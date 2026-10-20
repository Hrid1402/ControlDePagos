"""Órdenes urgentes (H18 y H19). Aquí la asistente las recupera y responde; TASK-63 agrega en este
mismo router crear, listar, cancelar y reenviar. Una ruta GET /ordenes/{id} debe declararse
después de /pendientes.

Errores: 401 NO_AUTENTICADO, SESION_REVOCADA o CUENTA_INACTIVA (también si cambia en medio de la
respuesta), 403 SIN_PERMISO (no es asistente), 404 NO_ENCONTRADO (orden inexistente o de otro
gerente), 422 VALIDACION y 409 ORDEN_DE_OTRA_ASISTENTE, ORDEN_CANCELADA, ORDEN_CERRADA,
ORDEN_ACEPTADA, ORDEN_NO_VALIDA (cambió el importe o la moneda) o los del inicio de pago:
PAGO_EN_CURSO, APROBACION_PENDIENTE, ESTADO_NO_PERMITIDO y SIN_SALDO.
"""

import uuid

from fastapi import APIRouter

from app.api.v1.pagos import deuda_salida
from app.core.dependencias import OrigenSolicitud, SesionDb, SoloAsistente
from app.core.paginacion import Pagina, ParametrosPagina, paginar
from app.schemas.ordenes import (
    AceptarOrdenSalida,
    OrdenAccionSalida,
    OrdenAsistenteSalida,
    RechazarOrdenEntrada,
)
from app.services.ordenes import (
    aceptar_orden,
    consulta_pendientes,
    marcar_vista,
    rechazar_orden,
    salida_orden,
)

router = APIRouter(prefix="/ordenes", tags=["ordenes"])


@router.get("/pendientes")
def pendientes(
    db: SesionDb, usuario: SoloAsistente, parametros: ParametrosPagina
) -> Pagina[OrdenAsistenteSalida]:
    """Órdenes enviadas o vistas, la más urgente primero. El cliente las pide al conectarse y al
    recibir resincronizar: cubre lo que llegó o se canceló mientras estaba sin conexión."""
    pagina = paginar(db, consulta_pendientes(usuario), parametros)
    return Pagina(
        items=[salida_orden(db, orden) for orden in pagina.items],
        total=pagina.total,
        page=pagina.page,
    )


@router.post("/{orden_id}/vista")
def vista(
    orden_id: uuid.UUID, db: SesionDb, usuario: SoloAsistente, origen: OrigenSolicitud
) -> OrdenAccionSalida:
    respuesta = marcar_vista(db, usuario, orden_id, origen=origen)
    db.commit()
    return OrdenAccionSalida(orden=salida_orden(db, respuesta.orden), repetido=respuesta.repetido)


@router.post("/{orden_id}/aceptar")
def aceptar(
    orden_id: uuid.UUID, db: SesionDb, usuario: SoloAsistente, origen: OrigenSolicitud
) -> AceptarOrdenSalida:
    """Acepta la orden y deja la deuda en proceso a nombre de la asistente."""
    aceptada = aceptar_orden(db, usuario, orden_id, origen=origen)
    db.commit()
    return AceptarOrdenSalida(
        orden=salida_orden(db, aceptada.orden),
        repetido=aceptada.repetido,
        resultado=aceptada.inicio.resultado,
        deuda=deuda_salida(db, aceptada.inicio.deuda),
    )


@router.post("/{orden_id}/rechazar")
def rechazar(
    orden_id: uuid.UUID,
    datos: RechazarOrdenEntrada,
    db: SesionDb,
    usuario: SoloAsistente,
    origen: OrigenSolicitud,
) -> OrdenAccionSalida:
    """«No puedo»: cierra la orden con el motivo y avisa al gerente. La deuda no cambia."""
    respuesta = rechazar_orden(db, usuario, orden_id, datos.motivo, datos.detalle, origen=origen)
    db.commit()
    return OrdenAccionSalida(orden=salida_orden(db, respuesta.orden), repetido=respuesta.repetido)
