"""Configuración de las deudas que se repiten cada mes (H11 CA04 y CA05, TASK-39).

Errores: 404 NO_ENCONTRADO (servicio ajeno o inexistente, o sin recurrencia al consultarla), 409
SERVICIO_DE_BAJA y 422 VALIDACION (servicio que no es de monto fijo ni variable, o monto fijo sin
monto).
"""

import uuid

from fastapi import APIRouter

from app.core.dependencias import GerenteId, OrigenSolicitud, SesionDb, UsuarioActual
from app.models import Recurrencia
from app.schemas.recurrencias import RecurrenciaEntrada, RecurrenciaSalida
from app.services.recurrencias import (
    DatosRecurrencia,
    configurar_recurrencia,
    obtener_recurrencia,
)

router = APIRouter(prefix="/servicios", tags=["recurrencias"])


def salida(recurrencia: Recurrencia) -> RecurrenciaSalida:
    return RecurrenciaSalida.model_validate(recurrencia, from_attributes=True)


@router.get("/{servicio_id}/recurrencia")
def ver(servicio_id: uuid.UUID, db: SesionDb, gerente_id: GerenteId) -> RecurrenciaSalida:
    return salida(obtener_recurrencia(db, servicio_id, gerente_id))


@router.put("/{servicio_id}/recurrencia")
def configurar(
    servicio_id: uuid.UUID,
    datos: RecurrenciaEntrada,
    db: SesionDb,
    usuario: UsuarioActual,
    gerente_id: GerenteId,
    origen: OrigenSolicitud,
) -> RecurrenciaSalida:
    recurrencia = configurar_recurrencia(
        db,
        usuario,
        gerente_id,
        servicio_id,
        DatosRecurrencia(
            monto=datos.monto,
            moneda=datos.moneda,
            dia_emision=datos.dia_emision,
            dia_vencimiento=datos.dia_vencimiento,
            activa=datos.activa,
        ),
        origen=origen,
    )
    db.commit()
    return salida(recurrencia)
