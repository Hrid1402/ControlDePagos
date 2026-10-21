"""Préstamos en cuotas (H11 CA07, TASK-40).

Con el total, el número de cuotas y la primera fecha se crea el préstamo y una deuda por cuota,
todas en la misma moneda. Las cuotas son iguales en céntimos y la última absorbe la diferencia,
para que la suma sea exactamente el total. Cada cuota vence el mismo día del mes que la primera;
si un mes no tiene ese día (31 en febrero), vence el último día de ese mes. Su periodo es el mes
de su vencimiento.

Solo los servicios de una categoría de tipo préstamo admiten préstamos. Si ya existe la misma
cuota del servicio en ese mes, el índice único de deudas lo rechaza con 409 DUPLICADO.
"""

import uuid
from dataclasses import dataclass
from datetime import date, datetime
from decimal import ROUND_DOWN, Decimal

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.dependencias import Origen
from app.core.errores import ErrorApi
from app.core.tiempo import ahora_lima, sumar_meses
from app.models import Categoria, Deuda, Prestamo, Usuario
from app.schemas.deudas import PrestamoEntrada
from app.services.auditoria import Accion, nombre_de, registrar_auditoria
from app.services.notificaciones import TipoNotificacion, notificar
from app.services.servicios import servicio_activo_propio


@dataclass(frozen=True)
class Cuota:
    numero: int
    vencimiento: date
    monto: Decimal


def cronograma(total: Decimal, cuotas: int, primera: date) -> list[Cuota]:
    base = (total / cuotas).quantize(Decimal("0.01"), ROUND_DOWN)
    ultima = total - base * (cuotas - 1)
    return [
        Cuota(i + 1, sumar_meses(primera, i), ultima if i == cuotas - 1 else base)
        for i in range(cuotas)
    ]


def crear_prestamo(
    db: Session,
    usuario: Usuario,
    gerente_id: uuid.UUID,
    datos: PrestamoEntrada,
    *,
    origen: Origen,
    ahora: datetime | None = None,
) -> tuple[Prestamo, list[Deuda]]:
    servicio = servicio_activo_propio(
        db, datos.servicio_id, gerente_id, bloquear=True, campo="servicio_id"
    )
    categoria = db.get(Categoria, servicio.categoria_id)
    if categoria is None or categoria.tipo != "prestamo":
        raise ErrorApi(
            422,
            "VALIDACION",
            "Elige un servicio de una categoría de préstamos para registrar sus cuotas.",
            "servicio_id",
        )
    plan = cronograma(datos.monto_total, datos.cuotas_total, datos.fecha_primera_cuota)
    prestamo = Prestamo(
        servicio_id=servicio.id,
        monto_total=datos.monto_total,
        cuotas_total=datos.cuotas_total,
        monto_cuota=plan[0].monto,
        fecha_primera_cuota=datos.fecha_primera_cuota,
        moneda=datos.moneda,
    )
    try:
        with db.begin_nested():
            db.add(prestamo)
            db.flush()
            deudas = [
                Deuda(
                    gerente_id=gerente_id,
                    servicio_id=servicio.id,
                    prestamo_id=prestamo.id,
                    cuota_numero=cuota.numero,
                    periodo=cuota.vencimiento.replace(day=1),
                    monto=cuota.monto,
                    moneda=datos.moneda,
                    fecha_vencimiento=cuota.vencimiento,
                    estado="pendiente",
                    origen="manual",
                    creado_por=usuario.id,
                )
                for cuota in plan
            ]
            db.add_all(deudas)
            db.flush()
    except IntegrityError as error:
        if "uq_deuda_periodo" not in str(error.orig):
            raise
        raise ErrorApi(
            409,
            "DUPLICADO",
            "El servicio ya tiene cuotas registradas en esos meses.",
            "fecha_primera_cuota",
        ) from None
    registrar_auditoria(
        db,
        usuario,
        Accion.PRESTAMO_CREADO,
        "prestamo",
        prestamo.id,
        {
            "servicio_id": servicio.id,
            "monto": datos.monto_total,
            "moneda": datos.moneda,
            "cuotas_total": datos.cuotas_total,
        },
        origen=origen,
    )
    if usuario.rol == "asistente":
        gerente = db.get(Usuario, gerente_id)
        if gerente is not None:
            notificar(
                db,
                gerente,
                TipoNotificacion.DEUDA_CREADA,
                "Préstamo registrado",
                f"{nombre_de(usuario)} registró un préstamo de {datos.moneda} "
                f"{datos.monto_total} en {datos.cuotas_total} cuotas.",
                clave_evento=f"prestamo_creado:{prestamo.id}",
                ahora=ahora or ahora_lima(),
            )
    return prestamo, deudas
