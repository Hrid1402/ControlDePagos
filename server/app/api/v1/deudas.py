"""Registro manual de deudas (H11, TASK-38). Gerente y asistente registran.

Errores: 404 NO_ENCONTRADO (servicio inexistente, eliminado o de otro gerente), 403
SIN_PERMISO, 422 VALIDACION, 409 SERVICIO_DE_BAJA y 409 DUPLICADO con deuda_existente (ya hay
una deuda activa del servicio en ese periodo). Una deuda vencida se registra con la advertencia.
El listado es de TASK-45 y el detalle de TASK-53.
"""

from fastapi import APIRouter, status

from app.core.dependencias import GerenteId, OrigenSolicitud, SesionDb, UsuarioActual
from app.schemas.deudas import AdvertenciasDeuda, DeudaEntrada, DeudaRegistradaSalida
from app.services.deudas import registrar_deuda, texto_periodo

router = APIRouter(prefix="/deudas", tags=["deudas"])


@router.post("", response_model=DeudaRegistradaSalida, status_code=status.HTTP_201_CREATED)
def registrar(
    datos: DeudaEntrada,
    db: SesionDb,
    usuario: UsuarioActual,
    gerente_id: GerenteId,
    origen: OrigenSolicitud,
) -> DeudaRegistradaSalida:
    registro = registrar_deuda(db, usuario, gerente_id, datos, origen)
    db.commit()
    deuda = registro.deuda
    # El registro manual exige monto positivo: nunca queda esperando recibo.
    assert deuda.monto is not None
    return DeudaRegistradaSalida(
        id=deuda.id,
        servicio_id=deuda.servicio_id,
        periodo=texto_periodo(deuda.periodo),
        monto=deuda.monto,
        moneda=deuda.moneda,
        fecha_vencimiento=deuda.fecha_vencimiento,
        numero_recibo=deuda.numero_recibo,
        estado=deuda.estado,
        origen=deuda.origen,
        creado_por=deuda.creado_por,
        creado_en=deuda.creado_en,
        advertencias=AdvertenciasDeuda(vencida=registro.vencida),
    )
