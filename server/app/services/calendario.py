"""Consulta de vencimientos del calendario, aislada por gerente."""

import uuid
from collections import defaultdict
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.tiempo import ahora_lima
from app.models import Deuda, Recurrencia, Servicio
from app.services.saldo import vencida

ESTADOS_PENDIENTES = frozenset(
    {
        "pendiente",
        "esperando_recibo",
        "esperando_aprobacion",
        "en_proceso",
        "por_validar",
        "pagada_parcial",
        "con_problema",
    }
)
ESTADOS_CALENDARIO = ESTADOS_PENDIENTES | {"pagada", "vencida"}


def vencimientos(
    db: Session,
    gerente_id: uuid.UUID,
    desde: date,
    hasta: date,
    categoria_id: uuid.UUID | None = None,
    estado: str | None = None,
    hoy: date | None = None,
) -> list[dict]:
    """Devuelve días ordenados con importes confirmados y proyecciones por moneda."""
    hoy = hoy or ahora_lima().date()
    consulta = (
        select(Deuda, Servicio, Recurrencia, vencida(hoy))
        .join(Servicio, Servicio.id == Deuda.servicio_id)
        .outerjoin(Recurrencia, Recurrencia.servicio_id == Servicio.id)
        .where(
            Deuda.gerente_id == gerente_id,
            Servicio.gerente_id == gerente_id,
            Deuda.fecha_vencimiento >= desde,
            Deuda.fecha_vencimiento <= hasta,
            Deuda.estado != "anulada",
        )
        .order_by(Deuda.fecha_vencimiento, Deuda.id)
    )
    if categoria_id is not None:
        consulta = consulta.where(Servicio.categoria_id == categoria_id)
    dias: dict[date, dict] = {}
    for deuda, servicio, recurrencia, es_vencida in db.execute(consulta):
        visible = "vencida" if es_vencida else deuda.estado
        if estado is not None and visible != estado:
            continue
        fecha = deuda.fecha_vencimiento
        dia = dias.setdefault(
            fecha,
            {
                "fecha": fecha,
                "deudas": [],
                "totales_confirmados": defaultdict(Decimal),
                "totales_proyectados": defaultdict(Decimal),
            },
        )
        proyeccion = recurrencia.monto if deuda.monto is None and recurrencia is not None else None
        dia["deudas"].append(
            {
                "id": deuda.id,
                "servicio_id": servicio.id,
                "categoria_id": servicio.categoria_id,
                "nombre": servicio.alias or servicio.empresa_nombre or "Servicio",
                "estado": visible,
                "monto": deuda.monto,
                "monto_proyectado": proyeccion,
                "moneda": deuda.moneda,
                "fecha_vencimiento": fecha,
            }
        )
        if deuda.monto is not None:
            dia["totales_confirmados"][deuda.moneda] += deuda.monto
        elif proyeccion is not None:
            dia["totales_proyectados"][deuda.moneda] += proyeccion
    return [
        {
            **dia,
            "totales_confirmados": dict(dia["totales_confirmados"]),
            "totales_proyectados": dict(dia["totales_proyectados"]),
        }
        for dia in dias.values()
    ]
