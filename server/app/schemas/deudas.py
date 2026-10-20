"""Esquemas del registro manual de deudas (H11, TASK-38).

El periodo viaja como AAAA-MM y se guarda como el primer día de ese mes (ck_deuda_periodo).
Aquí no se reciben fecha de emisión, campos de tarjeta o de préstamo (TASK-40) ni el recibo
adjunto (TASK-84). Tampoco estado ni origen: el registro manual siempre crea una deuda pendiente.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, Field, StringConstraints, field_validator

Moneda = Literal["PEN", "USD"]
# Igual que numeric(12,2): hasta 9 999 999 999.99, siempre positivo.
Monto = Annotated[Decimal, Field(gt=0, max_digits=12, decimal_places=2)]
Periodo = Annotated[str, StringConstraints(pattern=r"^[1-9]\d{3}-(0[1-9]|1[0-2])$")]
NumeroRecibo = Annotated[str, StringConstraints(strip_whitespace=True, max_length=60)]


class DeudaEntrada(BaseModel):
    """Obligatorios: servicio, monto positivo y vencimiento (CA01). Sin periodo se usa el mes del
    vencimiento; sin moneda, soles (CA09)."""

    servicio_id: uuid.UUID
    monto: Monto
    moneda: Moneda = "PEN"
    fecha_vencimiento: date
    periodo: Periodo | None = None
    numero_recibo: NumeroRecibo | None = None

    @field_validator("numero_recibo")
    @classmethod
    def vacio_como_ausente(cls, valor: str | None) -> str | None:
        return valor or None


class AdvertenciasDeuda(BaseModel):
    """vencida: el vencimiento ya pasó en Lima (CA02). Informa, no impide el registro."""

    vencida: bool


class DeudaRegistradaSalida(BaseModel):
    id: uuid.UUID
    servicio_id: uuid.UUID
    periodo: str
    monto: Decimal
    moneda: str
    fecha_vencimiento: date
    numero_recibo: str | None
    estado: str
    origen: str
    creado_por: uuid.UUID | None
    creado_en: datetime
    advertencias: AdvertenciasDeuda


class DeudaExistente(BaseModel):
    """Deuda activa que ocupa el servicio y el periodo: va en el 409 DUPLICADO (CA03). Puede no
    tener monto si espera su recibo."""

    id: uuid.UUID
    periodo: str
    estado: str
    monto: Decimal | None
    moneda: str
    fecha_vencimiento: date
