import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.services.pagos import ResultadoInicio

LARGO_MAXIMO_MOTIVO = 300


class CancelarInicioEntrada(BaseModel):
    """Motivo de la cancelación: opcional para el dueño del intento, obligatorio para el gerente
    que cancela el intento de otra persona."""

    motivo: str | None = Field(default=None, max_length=LARGO_MAXIMO_MOTIVO)

    @field_validator("motivo")
    @classmethod
    def sin_espacios(cls, valor: str | None) -> str | None:
        return (valor or "").strip() or None


class DeudaPagoSalida(BaseModel):
    """Estado de pago de la deuda. saldo es calculado: monto menos abonos validados."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    estado: str
    monto: Decimal | None
    moneda: str
    saldo: Decimal
    pago_iniciado_en: datetime | None
    pago_iniciado_por: uuid.UUID | None


class InicioPagoSalida(BaseModel):
    """iniciado abre la ventanilla; requiere_aprobacion espera la decisión del gerente. repetido
    indica que el mismo intento ya estaba registrado y no hubo efectos nuevos."""

    resultado: ResultadoInicio
    repetido: bool
    solicitud_id: uuid.UUID | None
    deuda: DeudaPagoSalida
