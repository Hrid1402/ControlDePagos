"""Edición con historial de montos y anulación de deudas (H11 CA10 y CA11, TASK-40).

Editar: gerente o asistente cambian lo que se envía. Confirmar el monto de una deuda que espera su
recibo la deja pendiente (CA05). Un monto que cambia queda en historial_monto y se avisa al otro
rol (CA10). Monto y moneda no cambian mientras hay un pago en curso, esperando aprobación o un
comprobante por validar: primero se resuelve el intento (contrato H11). Con abonos validados la
moneda ya no cambia y el monto no baja de lo abonado; si lo iguala, la deuda queda pagada.

Anular: solo el gerente, sin pago en curso, sin abonos y sin orden urgente abierta. La deuda queda
anulada, no se borra (CA11), y anularla otra vez no hace nada. Una deuda pagada o anulada no se
edita.

Las funciones no hacen commit. Las deudas se bloquean con el mismo orden que el pago (pagos.py).
"""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.dependencias import Origen, gerente_de
from app.core.errores import ErrorApi
from app.core.tiempo import ahora_lima
from app.models import Deuda, HistorialMonto, OrdenPago, Servicio, Usuario
from app.schemas.deudas import DeudaEdicion, validar_fechas_y_minimo
from app.services.auditoria import Accion, diferencias, nombre_de, registrar_auditoria
from app.services.notificaciones import TipoNotificacion, notificar
from app.services.pagos import bloquear_deuda
from app.services.saldo import aplicado_de

ESTADOS_CERRADOS = ("pagada", "anulada")
# Hay un intento de pago o un comprobante que aún puede cambiar el saldo.
ESTADOS_EN_CURSO = ("en_proceso", "por_validar", "esperando_aprobacion")
ESTADOS_ORDEN_ABIERTA = ("enviada", "vista", "aceptada")
CAMPOS = (
    "monto",
    "moneda",
    "fecha_vencimiento",
    "fecha_emision",
    "numero_recibo",
    "fecha_corte",
    "pago_minimo",
)


def conflicto(code: str, detalle: str) -> ErrorApi:
    return ErrorApi(409, code, detalle)


def otro_rol(db: Session, usuario: Usuario, gerente_id: uuid.UUID) -> Usuario | None:
    if usuario.rol == "asistente":
        return db.get(Usuario, gerente_id)
    return db.scalar(
        select(Usuario).where(
            Usuario.gerente_id == gerente_id,
            Usuario.rol == "asistente",
            Usuario.estado == "activa",
            Usuario.eliminado_en.is_(None),
        )
    )


def nombre_servicio(db: Session, deuda: Deuda) -> str:
    servicio = db.get(Servicio, deuda.servicio_id)
    return (servicio.alias or servicio.empresa_nombre or "la deuda") if servicio else "la deuda"


def editar_deuda(
    db: Session,
    usuario: Usuario,
    deuda_id: uuid.UUID,
    datos: DeudaEdicion,
    *,
    origen: Origen,
    ahora: datetime | None = None,
) -> Deuda:
    gerente_id = gerente_de(usuario)
    if gerente_id is None:
        raise ErrorApi(403, "SIN_PERMISO", "No tienes permiso para realizar esta acción.")
    deuda = bloquear_deuda(db, deuda_id, gerente_id)
    if deuda.estado in ESTADOS_CERRADOS:
        raise conflicto("ESTADO_NO_PERMITIDO", "Una deuda pagada o anulada ya no se edita.")
    cambios = {k: v for k, v in datos.model_dump(exclude_unset=True).items() if v is not None}
    antes: dict[str, Any] = {campo: getattr(deuda, campo) for campo in CAMPOS}
    nuevo_monto: Decimal | None = cambios.get("monto")
    cambia_monto = nuevo_monto is not None and nuevo_monto != deuda.monto
    cambia_moneda = "moneda" in cambios and cambios["moneda"] != deuda.moneda
    if (cambia_monto or cambia_moneda) and deuda.estado in ESTADOS_EN_CURSO:
        raise conflicto(
            "PAGO_EN_CURSO", "Resuelve el pago en curso antes de cambiar el monto o la moneda."
        )
    abonado = aplicado_de(db, deuda.id)
    if abonado > 0:
        if cambia_moneda:
            raise conflicto("CON_ABONOS", "La deuda tiene abonos: su moneda ya no puede cambiar.")
        if nuevo_monto is not None and nuevo_monto < abonado:
            raise ErrorApi(
                422,
                "VALIDACION",
                f"El monto no puede ser menor que lo ya abonado ({deuda.moneda} {abonado}).",
                "monto",
            )
    for campo, valor in cambios.items():
        setattr(deuda, campo, valor)
    if deuda.fecha_corte is not None and cambia_monto:
        deuda.pago_total = deuda.monto
    try:
        validar_fechas_y_minimo(
            deuda.monto,
            deuda.fecha_vencimiento,
            deuda.fecha_emision,
            deuda.fecha_corte,
            deuda.pago_minimo,
        )
    except ValueError as error:
        raise ErrorApi(422, "VALIDACION", str(error)) from None
    if deuda.estado == "esperando_recibo" and deuda.monto is not None:
        deuda.estado = "pendiente"
    if deuda.estado == "pagada_parcial" and deuda.monto is not None and abonado >= deuda.monto:
        deuda.estado = "pagada"
    if cambia_monto and antes["monto"] is not None and deuda.monto is not None:
        db.add(
            HistorialMonto(
                deuda_id=deuda.id,
                monto_anterior=antes["monto"],
                monto_nuevo=deuda.monto,
                origen="manual",
                usuario_id=usuario.id,
            )
        )
    cambiado = diferencias(antes, {campo: getattr(deuda, campo) for campo in CAMPOS})
    if not cambiado:
        return deuda
    registrar_auditoria(
        db,
        usuario,
        Accion.DEUDA_MONTO_CAMBIADO if cambia_monto else Accion.DEUDA_EDITADA,
        "deuda",
        deuda.id,
        {
            **cambiado,
            **(
                {"monto_anterior": antes["monto"], "monto_nuevo": deuda.monto}
                if cambia_monto
                else {}
            ),
        },
        origen=origen,
    )
    if cambia_monto:
        avisado = otro_rol(db, usuario, gerente_id)
        previo = f" de {deuda.moneda} {antes['monto']}" if antes["monto"] is not None else ""
        if avisado is not None:
            # No hay un tipo propio para el cambio de monto: va con el de las deudas registradas,
            # que es la preferencia con la que cada uno decide si recibir avisos de deudas.
            notificar(
                db,
                avisado,
                TipoNotificacion.DEUDA_CREADA,
                "Cambió el monto de una deuda",
                f"{nombre_de(usuario)} cambió el monto de {nombre_servicio(db, deuda)}{previo} "
                f"a {deuda.moneda} {deuda.monto}.",
                deuda_id=deuda.id,
                ahora=ahora or ahora_lima(),
            )
    return deuda


def anular_deuda(
    db: Session,
    gerente: Usuario,
    deuda_id: uuid.UUID,
    motivo: str | None,
    *,
    origen: Origen,
    ahora: datetime | None = None,
) -> Deuda:
    deuda = bloquear_deuda(db, deuda_id, gerente.id)
    if deuda.estado == "anulada":
        return deuda
    if deuda.estado == "pagada":
        raise conflicto("ESTADO_NO_PERMITIDO", "Una deuda pagada no se anula.")
    if deuda.estado in ESTADOS_EN_CURSO:
        raise conflicto("PAGO_EN_CURSO", "Resuelve el pago en curso antes de anular la deuda.")
    if aplicado_de(db, deuda.id) > 0:
        raise conflicto("CON_ABONOS", "La deuda tiene abonos validados: no se puede anular.")
    orden = db.scalar(
        select(OrdenPago.id).where(
            OrdenPago.deuda_id == deuda.id, OrdenPago.estado.in_(ESTADOS_ORDEN_ABIERTA)
        )
    )
    if orden is not None:
        raise conflicto("ORDEN_ABIERTA", "Cancela primero la orden urgente de esta deuda.")
    anterior = deuda.estado
    deuda.estado = "anulada"
    deuda.fijada = False
    registrar_auditoria(
        db,
        gerente,
        Accion.DEUDA_ANULADA,
        "deuda",
        deuda.id,
        {"estado_anterior": anterior, "estado_nuevo": "anulada", "motivo": motivo},
        origen=origen,
    )
    asistente = otro_rol(db, gerente, gerente.id)
    if asistente is not None:
        notificar(
            db,
            asistente,
            TipoNotificacion.DEUDA_CREADA,
            "Deuda anulada",
            f"{nombre_de(gerente)} anuló {nombre_servicio(db, deuda)}: ya no se cobra.",
            deuda_id=deuda.id,
            ahora=ahora or ahora_lima(),
        )
    return deuda
