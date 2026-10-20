"""Respuesta del calendario: los importes sin recibo se muestran aparte."""

import uuid
from datetime import date
from decimal import Decimal

from pydantic import BaseModel


class Vencimiento(BaseModel):
    id: uuid.UUID
    servicio_id: uuid.UUID
    categoria_id: uuid.UUID
    nombre: str
    estado: str
    monto: Decimal | None
    monto_proyectado: Decimal | None
    moneda: str
    fecha_vencimiento: date


class DiaCalendario(BaseModel):
    fecha: date
    deudas: list[Vencimiento]
    totales_confirmados: dict[str, Decimal]
    totales_proyectados: dict[str, Decimal]


class CalendarioSalida(BaseModel):
    dias: list[DiaCalendario]
