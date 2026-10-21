"""Inicio, declaración y cancelación del pago presencial (H22, compartido con H05, H19 y H23).

Errores: 404 NO_ENCONTRADO (deuda inexistente o de otro gerente), 403 SIN_PERMISO y 409
PAGO_EN_CURSO, APROBACION_PENDIENTE, ESTADO_NO_PERMITIDO, SIN_SALDO, SIN_INTENTO,
PAGO_DECLARADO o COMPROBANTE_ACTIVO. Superar el límite no es un error: responde 200 con
resultado requiere_aprobacion.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Body

from app.core.dependencias import OrigenSolicitud, SesionDb, UsuarioActual
from app.models import Deuda
from app.schemas.pagos import CancelarInicioEntrada, DeudaPagoSalida, InicioPagoSalida
from app.services.pagos import cancelar_inicio, iniciar_pago, marcar_pagada
from app.services.saldo import saldo_de

router = APIRouter(prefix="/deudas", tags=["pagos"])


def deuda_salida(db: SesionDb, deuda: Deuda) -> DeudaPagoSalida:
    return DeudaPagoSalida.model_validate(
        {
            "id": deuda.id,
            "estado": deuda.estado,
            "monto": deuda.monto,
            "moneda": deuda.moneda,
            "saldo": saldo_de(db, deuda),
            "pago_iniciado_en": deuda.pago_iniciado_en,
            "pago_iniciado_por": deuda.pago_iniciado_por,
            "pago_realizado": deuda.pago_realizado,
            "pago_realizado_en": deuda.pago_realizado_en,
        }
    )


@router.post("/{deuda_id}/iniciar-pago")
def iniciar(
    deuda_id: uuid.UUID, db: SesionDb, usuario: UsuarioActual, origen: OrigenSolicitud
) -> InicioPagoSalida:
    """Marca la deuda en proceso a nombre del usuario o crea la solicitud de aprobación."""
    inicio = iniciar_pago(db, usuario, deuda_id, origen=origen)
    db.commit()
    return InicioPagoSalida(
        resultado=inicio.resultado,
        repetido=inicio.repetido,
        solicitud_id=inicio.solicitud.id if inicio.solicitud else None,
        deuda=deuda_salida(db, inicio.deuda),
    )


@router.post("/{deuda_id}/marcar-pagada")
def marcar(
    deuda_id: uuid.UUID, db: SesionDb, usuario: UsuarioActual, origen: OrigenSolicitud
) -> DeudaPagoSalida:
    """Declara hecho el pago en curso; la deuda sigue en proceso hasta validar el comprobante."""
    deuda = marcar_pagada(db, usuario, deuda_id, origen=origen)
    db.commit()
    return deuda_salida(db, deuda)


@router.post("/{deuda_id}/cancelar-inicio")
def cancelar(
    deuda_id: uuid.UUID,
    db: SesionDb,
    usuario: UsuarioActual,
    origen: OrigenSolicitud,
    datos: Annotated[CancelarInicioEntrada | None, Body()] = None,
) -> DeudaPagoSalida:
    """Deshace un intento que no se pagó y vuelve la deuda a pendiente o pagada parcial."""
    motivo = datos.motivo if datos else None
    deuda = cancelar_inicio(db, usuario, deuda_id, motivo, origen=origen)
    db.commit()
    return deuda_salida(db, deuda)
