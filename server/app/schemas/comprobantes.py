import uuid
from decimal import Decimal

from pydantic import BaseModel, Field


class RepartoComprobanteEntrada(BaseModel):
    deuda_id: uuid.UUID
    monto_aplicado: Decimal = Field(gt=0, max_digits=12, decimal_places=2)


class ComprobanteSalida(BaseModel):
    id: uuid.UUID
    estado: str
    archivo_url: str
    hash_sha256: str
    motivo_codigo: str | None
