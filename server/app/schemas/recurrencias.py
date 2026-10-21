"""Deudas que se repiten cada mes (H11 CA04 y CA05, TASK-39)."""

import uuid
from datetime import date

from pydantic import BaseModel, Field

from app.schemas.deudas import Moneda, Monto

Dia = int


class RecurrenciaEntrada(BaseModel):
    """monto es obligatorio en un servicio de monto fijo; en uno variable se ignora, porque el de
    cada mes llega con su recibo. Sin dia_emision la deuda se crea el día 1 de cada mes."""

    monto: Monto | None = None
    moneda: Moneda = "PEN"
    dia_emision: Dia | None = Field(default=None, ge=1, le=31)
    dia_vencimiento: Dia = Field(ge=1, le=31)
    activa: bool = True


class RecurrenciaSalida(BaseModel):
    id: uuid.UUID
    servicio_id: uuid.UUID
    tipo: str
    monto: Monto | None
    moneda: str
    dia_emision: int | None
    dia_vencimiento: int
    activa: bool
    ultima_generacion: date | None
