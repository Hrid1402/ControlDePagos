"""Inicio, reserva y cancelación del pago presencial: servicio común de H05, H19, H22, H23 y H28.

El intento vive en la deuda: en_proceso con su dueño (pago_iniciado_por) y su fecha
(pago_iniciado_en). No se crean filas en pago, que es del pago automático (H21) y exige un medio
de pago. La reserva no se guarda: es el saldo de las deudas en proceso (app/services/saldo.py).

Las funciones no hacen commit, como la auditoría y las notificaciones: quien llama confirma. Así
aceptar una orden e iniciar su deuda es una sola transacción (TASK-68) y la ruta procesa cada
deuda de un lote en su propio savepoint (TASK-79).

Orden de bloqueo, el mismo en toda transacción para no caer en un interbloqueo:
orden_pago -> limite -> deuda -> solicitud_aprobacion. El límite del gerente se bloquea antes de
leer el consumo: dos pagos simultáneos del mismo gerente se turnan y el segundo ya ve la reserva
del primero. Sin fila de límite no hay límite en soles y no hace falta turnarse.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.dependencias import Origen, gerente_de
from app.core.errores import ErrorApi
from app.core.tiempo import ahora_lima, zona_horaria
from app.models import Deuda, Limite, OrdenPago, SolicitudAprobacion, Usuario
from app.services.auditoria import Accion, nombre_de, registrar_auditoria
from app.services.notificaciones import TipoNotificacion, notificar
from app.services.saldo import MONEDA_LIMITE, consumo_mes_pen, saldo_de

ESTADOS_INICIABLES = ("pendiente", "pagada_parcial")

MENSAJES_ESTADO = {
    "esperando_recibo": "La deuda aún no tiene monto: espera el recibo del mes.",
    "por_validar": "La deuda tiene un comprobante en revisión; espera a que se resuelva.",
    "pagada": "La deuda ya está pagada.",
    "anulada": "La deuda está anulada.",
    "con_problema": "La deuda tiene un problema reportado que debe resolver el gerente.",
}


class ResultadoInicio(StrEnum):
    INICIADO = "iniciado"
    REQUIERE_APROBACION = "requiere_aprobacion"


class Autorizacion(StrEnum):
    """Por qué se permite el pago; queda en el detalle de la auditoría."""

    GERENTE = "gerente"
    ORDEN = "orden"
    APROBACION = "aprobacion"
    LIMITE = "limite"


class MotivoAprobacion(StrEnum):
    MONEDA = "moneda"
    LIMITE_POR_PAGO = "limite_por_pago"
    LIMITE_MENSUAL = "limite_mensual"


@dataclass(frozen=True)
class AutorizacionOrden:
    """Orden urgente que autoriza el pago de una asistente. orden_pago no guarda importe ni
    moneda: la moneda autorizada la aporta quien acepta la orden (la que mostró en pantalla) y el
    importe exacto lo verifica TASK-63/68 antes de llamar a iniciar_pago."""

    orden: OrdenPago
    moneda: str


@dataclass(frozen=True)
class InicioPago:
    resultado: ResultadoInicio
    deuda: Deuda
    saldo: Decimal
    solicitud: SolicitudAprobacion | None = None
    repetido: bool = False


def sin_permiso() -> ErrorApi:
    return ErrorApi(403, "SIN_PERMISO", "No tienes permiso para realizar esta acción.")


def bloquear_limite(db: Session, gerente_id: uuid.UUID) -> Limite | None:
    return db.scalar(
        select(Limite)
        .where(Limite.gerente_id == gerente_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )


def bloquear_deuda(db: Session, deuda_id: uuid.UUID, gerente_id: uuid.UUID) -> Deuda:
    """Deuda del gerente bloqueada hasta el commit; si no existe o es ajena, el mismo 404."""
    deuda = db.scalar(
        select(Deuda)
        .where(Deuda.id == deuda_id, Deuda.gerente_id == gerente_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if deuda is None:
        raise ErrorApi(404, "NO_ENCONTRADO", "No se encontró el recurso solicitado.")
    return deuda


def solicitud_pendiente(db: Session, deuda_id: uuid.UUID) -> SolicitudAprobacion | None:
    return db.scalar(
        select(SolicitudAprobacion).where(
            SolicitudAprobacion.deuda_id == deuda_id, SolicitudAprobacion.estado == "pendiente"
        )
    )


def aprobacion_vigente(db: Session, deuda: Deuda, saldo: Decimal) -> SolicitudAprobacion | None:
    """Aprobación de este importe y esta moneda. Sirve mientras ambos sigan iguales, también tras
    cancelar un inicio; si cambia cualquiera de los dos hace falta otra solicitud."""
    return db.scalar(
        select(SolicitudAprobacion)
        .where(
            SolicitudAprobacion.deuda_id == deuda.id,
            SolicitudAprobacion.estado == "aprobada",
            SolicitudAprobacion.monto == saldo,
            SolicitudAprobacion.moneda == deuda.moneda,
        )
        .order_by(SolicitudAprobacion.resuelta_en.desc(), SolicitudAprobacion.id.desc())
        .limit(1)
    )


def validar_orden(autorizacion: AutorizacionOrden, deuda: Deuda, usuario: Usuario) -> None:
    orden = autorizacion.orden
    if (
        orden.estado != "aceptada"
        or orden.deuda_id != deuda.id
        or orden.asistente_id != usuario.id
        or autorizacion.moneda != deuda.moneda
    ):
        raise ErrorApi(
            409, "ORDEN_NO_VALIDA", "La orden ya no autoriza este pago. Revisa la deuda de nuevo."
        )


def motivo_aprobacion(
    db: Session, deuda: Deuda, saldo: Decimal, limite: Limite | None, ahora: datetime
) -> MotivoAprobacion | None:
    """Por qué el pago de una asistente necesita aprobación, o None si está dentro del límite.
    USD no se suma a los límites en soles: siempre pide aprobación expresa."""
    if deuda.moneda != MONEDA_LIMITE:
        return MotivoAprobacion.MONEDA
    if limite is None:
        return None
    if limite.por_pago is not None and saldo > limite.por_pago:
        return MotivoAprobacion.LIMITE_POR_PAGO
    if limite.mensual is not None:
        if consumo_mes_pen(db, deuda.gerente_id, ahora) + saldo > limite.mensual:
            return MotivoAprobacion.LIMITE_MENSUAL
    return None


def solicitar_aprobacion(
    db: Session,
    usuario: Usuario,
    deuda: Deuda,
    saldo: Decimal,
    motivo: MotivoAprobacion,
    origen: Origen,
    ahora: datetime,
) -> InicioPago:
    """Crea la solicitud por el saldo y deja la deuda esperando aprobación."""
    solicitud = SolicitudAprobacion(
        deuda_id=deuda.id, asistente_id=usuario.id, monto=saldo, moneda=deuda.moneda
    )
    try:
        with db.begin_nested():
            db.add(solicitud)
            db.flush()
    except IntegrityError as error:
        if "uq_solicitud_aprobacion_pendiente" not in str(error.orig):
            raise
        raise ErrorApi(
            409, "APROBACION_PENDIENTE", "La deuda ya tiene una solicitud de aprobación pendiente."
        ) from error
    anterior = deuda.estado
    deuda.estado = "esperando_aprobacion"
    registrar_auditoria(
        db,
        usuario,
        Accion.APROBACION_SOLICITADA,
        "deuda",
        deuda.id,
        {
            "solicitud_id": solicitud.id,
            "monto": saldo,
            "moneda": deuda.moneda,
            "motivo": motivo.value,
            "estado_anterior": anterior,
        },
        origen=origen,
    )
    gerente = db.get(Usuario, deuda.gerente_id)
    if gerente is not None:
        notificar(
            db,
            gerente,
            TipoNotificacion.APROBACION_PENDIENTE,
            "Pago por aprobar",
            f"{nombre_de(usuario)} pide aprobar un pago de {deuda.moneda} {saldo}.",
            deuda_id=deuda.id,
            urgente=deuda.fecha_vencimiento <= ahora.astimezone(zona_horaria()).date(),
            clave_evento=f"aprobacion_pendiente:{solicitud.id}",
        )
    return InicioPago(ResultadoInicio.REQUIERE_APROBACION, deuda, saldo, solicitud)


def iniciar_pago(
    db: Session,
    usuario: Usuario,
    deuda_id: uuid.UUID,
    *,
    origen: Origen,
    orden: AutorizacionOrden | None = None,
    ahora: datetime | None = None,
) -> InicioPago:
    """Inicia el pago presencial de la deuda o, si supera lo autorizado, pide la aprobación.

    Repetir el mismo intento (misma deuda y mismo usuario) devuelve el resultado vigente sin
    efectos nuevos; el intento o la solicitud de otra persona responde 409.
    """
    gerente_id = gerente_de(usuario)
    if gerente_id is None:
        raise sin_permiso()
    momento = ahora or ahora_lima()
    es_asistente = usuario.rol == "asistente"
    limite = bloquear_limite(db, gerente_id) if es_asistente else None
    deuda = bloquear_deuda(db, deuda_id, gerente_id)

    if deuda.estado == "en_proceso":
        if deuda.pago_iniciado_por != usuario.id:
            raise ErrorApi(409, "PAGO_EN_CURSO", "Otra persona ya está pagando esta deuda.")
        return InicioPago(ResultadoInicio.INICIADO, deuda, saldo_de(db, deuda), repetido=True)
    if deuda.estado == "esperando_aprobacion":
        solicitud = solicitud_pendiente(db, deuda.id)
        if solicitud is None or solicitud.asistente_id != usuario.id:
            raise ErrorApi(
                409,
                "APROBACION_PENDIENTE",
                "La deuda espera la decisión del gerente sobre una solicitud de aprobación.",
            )
        return InicioPago(
            ResultadoInicio.REQUIERE_APROBACION,
            deuda,
            saldo_de(db, deuda),
            solicitud,
            repetido=True,
        )
    if deuda.estado not in ESTADOS_INICIABLES:
        mensaje = MENSAJES_ESTADO.get(deuda.estado, "El estado de la deuda no permite pagarla.")
        raise ErrorApi(409, "ESTADO_NO_PERMITIDO", mensaje)

    saldo = saldo_de(db, deuda)
    if saldo <= 0:
        raise ErrorApi(409, "SIN_SALDO", "La deuda no tiene saldo pendiente.")

    detalle: dict[str, object] = {"estado_anterior": deuda.estado, "saldo": saldo}
    if not es_asistente:
        autorizacion = Autorizacion.GERENTE
    elif orden is not None:
        validar_orden(orden, deuda, usuario)
        autorizacion = Autorizacion.ORDEN
        detalle["orden_id"] = orden.orden.id
    elif (aprobada := aprobacion_vigente(db, deuda, saldo)) is not None:
        autorizacion = Autorizacion.APROBACION
        detalle["solicitud_id"] = aprobada.id
    else:
        motivo = motivo_aprobacion(db, deuda, saldo, limite, momento)
        if motivo is not None:
            return solicitar_aprobacion(db, usuario, deuda, saldo, motivo, origen, momento)
        autorizacion = Autorizacion.LIMITE

    deuda.estado = "en_proceso"
    deuda.pago_iniciado_por = usuario.id
    deuda.pago_iniciado_en = momento
    deuda.pago_realizado = False
    deuda.recordatorios_enviados = 0
    detalle |= {"moneda": deuda.moneda, "autorizacion": autorizacion.value}
    registrar_auditoria(
        db, usuario, Accion.PAGO_INICIADO, "deuda", deuda.id, detalle, origen=origen
    )
    return InicioPago(ResultadoInicio.INICIADO, deuda, saldo)
