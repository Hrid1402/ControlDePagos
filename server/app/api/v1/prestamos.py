"""Préstamos en cuotas (H11 CA07, TASK-40).

Errores: 404 NO_ENCONTRADO (servicio ajeno o inexistente), 409 SERVICIO_DE_BAJA, 422 VALIDACION
(servicio que no es de préstamos, total o cuotas inválidos) y 409 DUPLICADO (ya hay cuotas del
servicio en esos meses).
"""

from decimal import Decimal

from fastapi import APIRouter, status

from app.core.dependencias import GerenteId, OrigenSolicitud, SesionDb, UsuarioActual
from app.schemas.deudas import CuotaSalida, PrestamoEntrada, PrestamoSalida
from app.services.prestamos import crear_prestamo

router = APIRouter(prefix="/prestamos", tags=["prestamos"])


@router.post("", status_code=status.HTTP_201_CREATED)
def crear(
    datos: PrestamoEntrada,
    db: SesionDb,
    usuario: UsuarioActual,
    gerente_id: GerenteId,
    origen: OrigenSolicitud,
) -> PrestamoSalida:
    prestamo, deudas = crear_prestamo(db, usuario, gerente_id, datos, origen=origen)
    db.commit()
    return PrestamoSalida(
        id=prestamo.id,
        servicio_id=prestamo.servicio_id,
        monto_total=prestamo.monto_total,
        cuotas_total=prestamo.cuotas_total,
        monto_cuota=prestamo.monto_cuota,
        moneda=prestamo.moneda,
        cuotas=[
            CuotaSalida(
                deuda_id=d.id,
                cuota_numero=d.cuota_numero or 0,
                fecha_vencimiento=d.fecha_vencimiento,
                monto=d.monto or Decimal(0),
            )
            for d in deudas
        ],
    )
