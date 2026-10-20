"""Esquemas para límites de gasto y solicitudes de aprobación (H05, TASK-22).

Reutiliza las tablas limite y solicitud_aprobacion existentes en el esquema.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class ConfigurarLimiteEntrada(BaseModel):
    """Límites en soles con hasta 2 decimales; null es sin límite (CA02 y CA03). Que el límite
    por pago no supere al mensual lo valida fijar_limite, que marca el campo por_pago: un
    validador entre campos aquí respondería sin campo."""

    por_pago: Decimal | None = Field(default=None, gt=0, max_digits=12, decimal_places=2)
    mensual: Decimal | None = Field(default=None, gt=0, max_digits=12, decimal_places=2)


class ConsumoMesSalida(BaseModel):
    """Consumo PEN del mes en Lima: abonos validados de la asistente y reservas en proceso."""

    validado: Decimal
    reservado: Decimal
    total: Decimal


class LimitesConsumoSalida(BaseModel):
    """Límites del gerente con el consumo del mes frente a ellos (CA04). Sin configurar, los dos
    límites son null y actualizado_en también."""

    por_pago: Decimal | None
    mensual: Decimal | None
    actualizado_en: datetime | None
    mes: str
    consumo: ConsumoMesSalida


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


class SolicitudListaSalida(SolicitudAprobacionSalida):
    """Solicitud con lo que la lista muestra junto a ella (CA10): servicio, vencimiento y los
    nombres de quien la pidió y de quien la resolvió."""

    servicio: str
    fecha_vencimiento: date
    asistente: str
    resuelta_por_nombre: str | None


class RechazarSolicitudEntrada(BaseModel):
    """Motivo opcional del rechazo, que recibe la asistente (CA08)."""

    motivo: str | None = Field(default=None, max_length=300)
