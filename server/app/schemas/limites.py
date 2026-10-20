"""Esquemas para límites de gasto y solicitudes de aprobación (H05, TASK-22).

Reutiliza las tablas limite y solicitud_aprobacion existentes en el esquema.
"""

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ConfigurarLimiteEntrada(BaseModel):
    """Importes opcionales para fijar topes de pago (CA02 y CA03)."""

    por_pago: Decimal | None = Field(default=None, gt=0, decimal_places=2)
    mensual: Decimal | None = Field(default=None, gt=0, decimal_places=2)

    @model_validator(mode="after")
    def validar_por_pago_no_supera_mensual(self) -> "ConfigurarLimiteEntrada":
        if self.por_pago is not None and self.mensual is not None:
            if self.por_pago > self.mensual:
                raise ValueError("El límite por pago no puede ser mayor que el mensual.")
        return self


class LimiteSalida(BaseModel):
    """Datos de los límites configurados para el gerente."""

    model_config = ConfigDict(from_attributes=True)

    gerente_id: uuid.UUID
    por_pago: Decimal | None
    mensual: Decimal | None
    creado_en: datetime
    actualizado_en: datetime


class SolicitudAprobacionSalida(BaseModel):
    """Detalle de una solicitud de aprobación vinculada a una deuda."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    deuda_id: uuid.UUID
    asistente_id: uuid.UUID
    monto: Decimal
    moneda: str
    estado: str
    motivo: str | None
    recordatorios_enviados: int
    resuelta_por: uuid.UUID | None
    resuelta_en: datetime | None
    creado_en: datetime
    actualizado_en: datetime
