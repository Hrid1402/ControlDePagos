import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field


class RepartoComprobanteEntrada(BaseModel):
    deuda_id: uuid.UUID
    # Sin monto se aplica todo el saldo por cubrir de la deuda.
    monto_aplicado: Decimal | None = Field(default=None, gt=0, max_digits=12, decimal_places=2)


class AprobarEntrada(BaseModel):
    """Sin deudas se aplica el reparto confirmado al subir; con deudas, el gerente lo corrige."""

    deudas: list[RepartoComprobanteEntrada] | None = None


class RechazarEntrada(BaseModel):
    motivo: str = Field(min_length=1, max_length=500, pattern=r"\S")


class RepartoSalida(BaseModel):
    deuda_id: uuid.UUID
    monto_aplicado: Decimal


class ComprobanteSalida(BaseModel):
    """Estado del comprobante. archivo_enlace es un enlace firmado de 5 minutos: la ruta privada
    del archivo no sale de la API."""

    id: uuid.UUID
    estado: str
    motivo_codigo: str | None
    # Motivo y acción a seguir en palabras, para mostrar con el resultado (CA03).
    observacion: str | None
    archivo_tipo: str
    archivo_enlace: str | None
    moneda: str
    monto: Decimal | None
    entidad: str | None
    numero_operacion: str | None
    fecha_pago: datetime | None
    # Entidad y campos leídos con su confianza, faltantes y, si fue duplicado de un comprobante
    # propio, cuál y en qué deudas se usó.
    datos_extraidos: dict[str, Any]
    deuda_sugerida_id: uuid.UUID | None
    reemplaza_a_id: uuid.UUID | None
    reemplazado_por_id: uuid.UUID | None
    subido_por: uuid.UUID
    creado_en: datetime
    revisado_en: datetime | None
    deudas: list[RepartoSalida]
