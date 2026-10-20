"""Servicio de límites y solicitudes de aprobación (H05, TASK-22 y TASK-24).

Reutiliza los modelos Limite y SolicitudAprobacion existentes sobre el esquema. La solicitud la
crea el inicio de pago (app/services/pagos.py); aquí se lista, se resuelve y se recuerda.

Resolver sigue el orden de bloqueo de pagos.py: deuda y luego solicitud_aprobacion. Aprobar
autoriza solo el importe y la moneda de la solicitud: no inicia ni paga la deuda, que vuelve a su
estado anterior para que la asistente inicie el pago (aprobacion_vigente lo reconoce).
"""

import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from app.core.dependencias import Origen
from app.core.errores import ErrorApi
from app.core.tiempo import ahora_lima, zona_horaria
from app.models import Deuda, Limite, Notificacion, Servicio, SolicitudAprobacion, Usuario
from app.services.auditoria import Accion, nombre_de, registrar_auditoria
from app.services.notificaciones import TipoNotificacion, notificar
from app.services.pagos import bloquear_deuda
from app.services.saldo import aplicado_de

DECISIONES = ("aprobada", "rechazada")
LARGO_MOTIVO = 300
# CA09: mientras siga pendiente, un recordatorio por cada 2 horas desde que se pidió.
INTERVALO_RECORDATORIO = timedelta(hours=2)


def obtener_limite(db: Session, gerente_id: uuid.UUID) -> Limite | None:
    """Devuelve la configuración de límites del gerente si existe."""
    return db.get(Limite, gerente_id)


def fijar_limite(
    db: Session,
    gerente_id: uuid.UUID,
    por_pago: Decimal | None = None,
    mensual: Decimal | None = None,
) -> Limite:
    """Crea o actualiza los límites opcionales del gerente validando las reglas de negocio."""
    if por_pago is not None and por_pago <= Decimal("0"):
        raise ErrorApi(
            400, "MONTO_INVALIDO", "El límite por pago debe ser mayor que cero.", "por_pago"
        )
    if mensual is not None and mensual <= Decimal("0"):
        raise ErrorApi(
            400, "MONTO_INVALIDO", "El límite mensual debe ser mayor que cero.", "mensual"
        )
    if por_pago is not None and mensual is not None and por_pago > mensual:
        raise ErrorApi(
            400,
            "LIMITE_INVALIDO",
            "El límite por pago no puede ser mayor que el mensual.",
            "por_pago",
        )

    limite = db.get(Limite, gerente_id)
    if limite is None:
        limite = Limite(gerente_id=gerente_id, por_pago=por_pago, mensual=mensual)
        db.add(limite)
    else:
        limite.por_pago = por_pago
        limite.mensual = mensual

    db.flush()
    return limite


def consulta_solicitudes(
    gerente_id: uuid.UUID, estado: str | None = None
) -> Select[SolicitudAprobacion]:
    """Solicitudes de las deudas del gerente, las más recientes primero (CA10)."""
    consulta = (
        select(SolicitudAprobacion)
        .join(Deuda, SolicitudAprobacion.deuda_id == Deuda.id)
        .where(Deuda.gerente_id == gerente_id)
    )
    if estado is not None:
        consulta = consulta.where(SolicitudAprobacion.estado == estado)
    return consulta.order_by(SolicitudAprobacion.creado_en.desc())


def solicitudes_de_gerente(
    db: Session,
    gerente_id: uuid.UUID,
    estado: str | None = None,
) -> list[SolicitudAprobacion]:
    """Obtiene las solicitudes vinculadas al equipo del gerente garantizando aislamiento tenant."""
    return list(db.scalars(consulta_solicitudes(gerente_id, estado)).all())


@dataclass(frozen=True)
class ContextoSolicitud:
    """Lo que la lista muestra junto a cada solicitud: deuda, servicio y personas."""

    servicio: str
    fecha_vencimiento: date
    asistente: str
    resuelta_por: str | None


def nombre_servicio(servicio: Servicio) -> str:
    return servicio.alias or servicio.empresa_nombre or "Servicio"


def contexto_de(
    db: Session, solicitudes: list[SolicitudAprobacion]
) -> dict[uuid.UUID, ContextoSolicitud]:
    """Contexto de una página de solicitudes en dos consultas, sin una por fila."""
    if not solicitudes:
        return {}
    filas = db.execute(
        select(Deuda.id, Deuda.fecha_vencimiento, Servicio)
        .join(Servicio, Deuda.servicio_id == Servicio.id)
        .where(Deuda.id.in_({s.deuda_id for s in solicitudes}))
    ).all()
    deudas = {fila[0]: (fila[1], nombre_servicio(fila[2])) for fila in filas}
    ids = {s.asistente_id for s in solicitudes} | {
        s.resuelta_por for s in solicitudes if s.resuelta_por is not None
    }
    personas = {u.id: nombre_de(u) for u in db.scalars(select(Usuario).where(Usuario.id.in_(ids)))}
    contexto = {}
    for s in solicitudes:
        vence, servicio = deudas[s.deuda_id]
        contexto[s.id] = ContextoSolicitud(
            servicio=servicio,
            fecha_vencimiento=vence,
            asistente=personas.get(s.asistente_id, "Asistente"),
            resuelta_por=personas.get(s.resuelta_por) if s.resuelta_por else None,
        )
    return contexto


def resolver_solicitud(
    db: Session,
    gerente: Usuario,
    solicitud_id: uuid.UUID,
    estado: str,
    motivo: str | None = None,
    *,
    origen: Origen | None = None,
    ahora: datetime | None = None,
) -> SolicitudAprobacion:
    """Aprueba o rechaza una solicitud pendiente y avisa a la asistente (CA07 y CA08).

    Repetir la misma decisión devuelve la solicitud sin efectos nuevos; la decisión contraria
    sobre una solicitud ya resuelta responde 409. Aprobar solo autoriza el importe y la moneda de
    la solicitud: si la deuda cambia, hace falta otra (CA12).
    """
    if estado not in DECISIONES:
        raise ErrorApi(400, "ESTADO_INVALIDO", f"El estado '{estado}' no es válido.")
    no_encontrada = ErrorApi(404, "NO_ENCONTRADO", "No se encontró la solicitud de aprobación.")
    deuda_id = db.scalar(
        select(SolicitudAprobacion.deuda_id)
        .join(Deuda, SolicitudAprobacion.deuda_id == Deuda.id)
        .where(SolicitudAprobacion.id == solicitud_id, Deuda.gerente_id == gerente.id)
    )
    if deuda_id is None:
        raise no_encontrada
    deuda = bloquear_deuda(db, deuda_id, gerente.id)
    solicitud = db.scalar(
        select(SolicitudAprobacion)
        .where(SolicitudAprobacion.id == solicitud_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if solicitud is None:
        raise no_encontrada
    if solicitud.estado == estado:
        return solicitud
    if solicitud.estado != "pendiente":
        raise ErrorApi(409, "SOLICITUD_YA_RESUELTA", "La solicitud ya ha sido resuelta.")

    momento = ahora or ahora_lima()
    # El motivo solo acompaña al rechazo (CA08).
    motivo = ((motivo or "").strip() or None) if estado == "rechazada" else None
    solicitud.estado = estado
    solicitud.motivo = motivo
    solicitud.resuelta_por = gerente.id
    solicitud.resuelta_en = momento

    anterior = deuda.estado
    if deuda.estado == "esperando_aprobacion":
        deuda.estado = "pagada_parcial" if aplicado_de(db, deuda.id) > 0 else "pendiente"

    if origen is not None:
        registrar_auditoria(
            db,
            gerente,
            Accion.APROBACION_APROBADA if estado == "aprobada" else Accion.APROBACION_RECHAZADA,
            "deuda",
            deuda.id,
            {
                "solicitud_id": solicitud.id,
                "monto": solicitud.monto,
                "moneda": solicitud.moneda,
                "motivo": motivo,
                "estado_anterior": anterior,
                "estado_nuevo": deuda.estado,
            },
            origen=origen,
        )

    asistente = db.get(Usuario, solicitud.asistente_id)
    if asistente is not None:
        servicio = db.get(Servicio, deuda.servicio_id)
        importe = f"{solicitud.moneda} {solicitud.monto}"
        nombre = nombre_servicio(servicio) if servicio else "la deuda"
        if estado == "aprobada":
            titulo = "Pago aprobado"
            mensaje = f"El gerente aprobó el pago de {importe} de {nombre}. Ya puedes iniciarlo."
        else:
            titulo = "Solicitud rechazada"
            mensaje = f"El gerente rechazó el pago de {importe} de {nombre}." + (
                f" Motivo: {motivo}" if motivo else ""
            )
        notificar(
            db,
            asistente,
            TipoNotificacion.APROBACION_PENDIENTE,
            titulo,
            mensaje,
            deuda.id,
            urgente=deuda.fecha_vencimiento <= momento.astimezone(zona_horaria()).date(),
            clave_evento=f"aprobacion_resuelta:{solicitud.id}",
            ahora=momento,
        )

    db.flush()
    return solicitud


def turno_de(solicitud: SolicitudAprobacion, ahora: datetime) -> int:
    """Turnos de 2 horas cumplidos desde que se pidió la aprobación."""
    return int((ahora - solicitud.creado_en) // INTERVALO_RECORDATORIO)


def clave_vence_hoy(solicitud: SolicitudAprobacion, hoy: date) -> str:
    return f"aprobacion_vence_hoy:{solicitud.id}:{hoy.isoformat()}"


def recordar_solicitud(
    db: Session,
    solicitud_id: uuid.UUID,
    hoy: date | None = None,
    *,
    ahora: datetime | None = None,
    numero: int | None = None,
    clave: str | None = None,
) -> SolicitudAprobacion:
    """Recuerda al gerente una solicitud pendiente; urgente si la deuda vence hoy o ya venció
    (CA09). numero es el turno que se recuerda (por defecto, el siguiente) y va en la clave del
    aviso: repetir el mismo turno no lo duplica."""
    solicitud = db.get(SolicitudAprobacion, solicitud_id)
    if solicitud is None or solicitud.estado != "pendiente":
        raise ErrorApi(404, "NO_ENCONTRADO", "Solicitud pendiente no encontrada.")

    deuda = db.get(Deuda, solicitud.deuda_id)
    if deuda is None:
        raise ErrorApi(404, "NO_ENCONTRADO", "Deuda no encontrada.")

    momento = ahora or ahora_lima()
    dia_actual = hoy or momento.astimezone(zona_horaria()).date()
    turno = numero if numero is not None else solicitud.recordatorios_enviados + 1
    solicitud.recordatorios_enviados = max(solicitud.recordatorios_enviados, turno)

    gerente = db.get(Usuario, deuda.gerente_id)
    asistente = db.get(Usuario, solicitud.asistente_id)
    if gerente is not None:
        servicio = db.get(Servicio, deuda.servicio_id)
        quien = nombre_de(asistente) if asistente else "Tu asistente"
        vence = "vence hoy" if deuda.fecha_vencimiento == dia_actual else "sigue pendiente"
        notificar(
            db,
            gerente,
            TipoNotificacion.APROBACION_PENDIENTE,
            "Recordatorio de aprobación",
            f"{quien} espera tu respuesta al pago de {solicitud.moneda} {solicitud.monto}"
            f" de {nombre_servicio(servicio) if servicio else 'una deuda'}: {vence}.",
            deuda.id,
            urgente=deuda.fecha_vencimiento <= dia_actual,
            clave_evento=clave or f"recordatorio_aprobacion:{solicitud.id}:{turno}",
            ahora=momento,
        )

    db.flush()
    return solicitud


def recordar_pendientes(db: Session, ahora: datetime | None = None) -> int:
    """Envía los recordatorios que tocan (CA09) y devuelve cuántos.

    - Uno por cada turno de 2 horas sin respuesta. Si el worker estuvo detenido, se envía solo el
      turno actual, no todos los atrasados.
    - El día en que la deuda vence, uno urgente de inmediato si ese día aún no se avisó; cuenta
      como el turno en curso para no enviar otro enseguida.

    Toma cada solicitud con bloqueo y salta las que otra transacción está resolviendo; resuelta,
    deja de estar pendiente y no se recuerda más.
    """
    momento = ahora or ahora_lima()
    hoy = momento.astimezone(zona_horaria()).date()
    enviados = 0
    pendientes = db.scalars(
        select(SolicitudAprobacion.id)
        .where(SolicitudAprobacion.estado == "pendiente")
        .order_by(SolicitudAprobacion.creado_en)
    ).all()
    for solicitud_id in pendientes:
        solicitud = db.scalar(
            select(SolicitudAprobacion)
            .where(
                SolicitudAprobacion.id == solicitud_id,
                SolicitudAprobacion.estado == "pendiente",
            )
            .with_for_update(skip_locked=True)
            .execution_options(populate_existing=True)
        )
        deuda = db.get(Deuda, solicitud.deuda_id) if solicitud else None
        if solicitud is None or deuda is None:
            continue
        turno = turno_de(solicitud, momento)
        pedida_antes = solicitud.creado_en.astimezone(zona_horaria()).date() < hoy
        clave = clave_vence_hoy(solicitud, hoy)
        if deuda.fecha_vencimiento <= hoy and pedida_antes and not ya_avisado(db, deuda, clave):
            recordar_solicitud(
                db,
                solicitud.id,
                ahora=momento,
                numero=max(turno, solicitud.recordatorios_enviados),
                clave=clave,
            )
        elif turno > solicitud.recordatorios_enviados:
            recordar_solicitud(db, solicitud.id, ahora=momento, numero=turno)
        else:
            continue
        enviados += 1
    return enviados


def ya_avisado(db: Session, deuda: Deuda, clave: str) -> bool:
    return (
        db.scalar(
            select(Notificacion.id).where(
                Notificacion.usuario_id == deuda.gerente_id, Notificacion.clave_evento == clave
            )
        )
        is not None
    )
