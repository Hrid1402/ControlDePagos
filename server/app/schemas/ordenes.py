import uuid
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, Field, field_validator

from app.schemas.pagos import DeudaPagoSalida
from app.services.pagos import ResultadoInicio

LARGO_MAXIMO_DETALLE = 300


class MotivoNoPago(StrEnum):
    """Motivos de «no puedo pagar» (H28, ck_reporte_problema_motivo). El rechazo de una orden y
    el reporte de TASK-71 usan el mismo catálogo."""

    PORTAL_CAIDO = "portal_caido"
    SALDO_INSUFICIENTE = "saldo_insuficiente"
    MONTO_DISTINTO = "monto_distinto"
    AGENTE_CERRADO = "agente_cerrado"
    OTRO_MEDIO = "otro_medio"
    OTRO = "otro"


class RechazarOrdenEntrada(BaseModel):
    """detalle es obligatorio con el motivo otro; el servicio lo valida."""

    motivo: MotivoNoPago
    detalle: str | None = Field(default=None, max_length=LARGO_MAXIMO_DETALLE)

    @field_validator("detalle")
    @classmethod
    def sin_espacios(cls, valor: str | None) -> str | None:
        return (valor or "").strip() or None


class OrdenAsistenteSalida(BaseModel):
    """Orden urgente como la ve la asistente en pantalla completa (H19 CA02). version cambia en
    cada transición o reenvío: el cliente descarta un evento con una version ya vista."""

    id: uuid.UUID
    deuda_id: uuid.UUID
    estado: str
    version: str
    plazo: datetime | None
    mensaje: str | None
    monto: Decimal
    moneda: str
    reenvios: int
    vista_en: datetime | None
    aceptada_en: datetime | None
    creado_en: datetime
    motivo: MotivoNoPago | None
    detalle: str | None
    empresa: str | None
    alias: str | None
    codigo_suministro: str
    lugar_pago: str | None
    fecha_vencimiento: date
    gerente_nombre: str


class OrdenAccionSalida(BaseModel):
    """repetido indica que la orden ya estaba en ese estado y no hubo efectos nuevos."""

    orden: OrdenAsistenteSalida
    repetido: bool


class AceptarOrdenSalida(OrdenAccionSalida):
    """La deuda queda en proceso a nombre de la asistente: abre la ventanilla (H19 CA10)."""

    resultado: ResultadoInicio
    deuda: DeudaPagoSalida
