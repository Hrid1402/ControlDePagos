"""Servicio de consulta y validación de límites y solicitudes (H05, TASK-22).

Reutiliza los modelos Limite y SolicitudAprobacion existentes sobre el esquema.
"""

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errores import ErrorApi
from app.models import Deuda, Limite, SolicitudAprobacion, Usuario


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


def solicitudes_de_gerente(
    db: Session,
    gerente_id: uuid.UUID,
    estado: str | None = None,
) -> list[SolicitudAprobacion]:
    """Obtiene las solicitudes vinculadas al equipo del gerente garantizando aislamiento tenant."""
    consulta = (
        select(SolicitudAprobacion)
        .join(Deuda, SolicitudAprobacion.deuda_id == Deuda.id)
        .where(Deuda.gerente_id == gerente_id)
    )
    if estado is not None:
        consulta = consulta.where(SolicitudAprobacion.estado == estado)

    consulta = consulta.order_by(SolicitudAprobacion.creado_en.desc())
    return list(db.scalars(consulta).all())


def resolver_solicitud(
    db: Session,
    gerente: Usuario,
    solicitud_id: uuid.UUID,
    estado: str,
    motivo: str | None = None,
) -> SolicitudAprobacion:
    """Aprueba o rechaza una solicitud de aprobación (CA07 y CA08)."""
    from datetime import UTC, datetime

    from app.services.notificaciones import TipoNotificacion, notificar

    if estado not in ("aprobada", "rechazada"):
        raise ErrorApi(400, "ESTADO_INVALIDO", f"El estado '{estado}' no es válido.")

    solicitud = db.get(SolicitudAprobacion, solicitud_id)
    if solicitud is None:
        raise ErrorApi(404, "NO_ENCONTRADO", "No se encontró la solicitud de aprobación.")

    deuda = db.get(Deuda, solicitud.deuda_id)
    if deuda is None or deuda.gerente_id != gerente.id:
        raise ErrorApi(404, "NO_ENCONTRADO", "No se encontró la solicitud de aprobación.")

    if solicitud.estado != "pendiente":
        raise ErrorApi(409, "SOLICITUD_YA_RESUELTA", "La solicitud ya ha sido resuelta.")

    solicitud.estado = estado
    solicitud.resuelta_por = gerente.id
    solicitud.resuelta_en = datetime.now(UTC)

    # La deuda deja de esperar aprobación y vuelve a estado pendiente
    if deuda.estado == "esperando_aprobacion":
        deuda.estado = "pendiente"

    if estado == "rechazada":
        solicitud.motivo = motivo
        asistente = db.get(Usuario, solicitud.asistente_id)
        if asistente is not None:
            notificar(
                db,
                asistente,
                TipoNotificacion.APROBACION_PENDIENTE,
                "Solicitud rechazada",
                f"El gerente rechazó la solicitud para la deuda {deuda.id}."
                + (f" Motivo: {motivo}" if motivo else ""),
                deuda.id,
                urgente=False,
            )

    db.flush()
    return solicitud


def recordar_solicitud(
    db: Session,
    solicitud_id: uuid.UUID,
    hoy: date | None = None,
) -> SolicitudAprobacion:
    """Envía un recordatorio de solicitud pendiente; urgente si la deuda vence hoy (CA09)."""
    from app.core.tiempo import ahora_lima
    from app.services.notificaciones import TipoNotificacion, notificar

    solicitud = db.get(SolicitudAprobacion, solicitud_id)
    if solicitud is None or solicitud.estado != "pendiente":
        raise ErrorApi(404, "NO_ENCONTRADO", "Solicitud pendiente no encontrada.")

    deuda = db.get(Deuda, solicitud.deuda_id)
    if deuda is None:
        raise ErrorApi(404, "NO_ENCONTRADO", "Deuda no encontrada.")

    solicitud.recordatorios_enviados += 1
    dia_actual = hoy or ahora_lima().date()
    es_urgente = deuda.fecha_vencimiento == dia_actual

    gerente = db.get(Usuario, deuda.gerente_id)
    if gerente is not None:
        notificar(
            db,
            gerente,
            TipoNotificacion.APROBACION_PENDIENTE,
            "Recordatorio de aprobación",
            f"La solicitud de S/ {solicitud.monto} sigue pendiente.",
            deuda.id,
            urgente=es_urgente,
        )

    db.flush()
    return solicitud
