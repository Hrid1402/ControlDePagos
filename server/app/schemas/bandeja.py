import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, StrictBool

from app.core.paginacion import Pagina
from app.services.bandeja import Etiqueta


class FijarEntrada(BaseModel):
    """Valor explícito en lugar de alternar: repetir la solicitud no deshace el cambio."""

    fijada: StrictBool


class DeudaPrioridadSalida(BaseModel):
    id: uuid.UUID
    fijada: bool
    oculta_hasta: datetime | None


class CategoriaBandeja(BaseModel):
    id: uuid.UUID
    nombre: str
    color: str
    icono: str
    tipo: str


class OrdenUrgenteBandeja(BaseModel):
    id: uuid.UUID
    estado: str
    plazo: datetime | None


class EnProcesoBandeja(BaseModel):
    """Quién está pagando la deuda (CA09): rol gerente o asistente."""

    usuario_id: uuid.UUID
    rol: str
    nombre: str
    desde: datetime | None


class ItemBandeja(BaseModel):
    """Deuda de la bandeja. nivel y etiqueta dan el motivo de la prioridad; saldo y
    dias_restantes son calculados (negativos si ya venció)."""

    id: uuid.UUID
    empresa: str | None
    alias: str | None
    codigo_suministro: str
    lugar_pago: str | None
    categoria: CategoriaBandeja
    monto: Decimal | None
    moneda: str
    saldo: Decimal | None
    estado: str
    fecha_vencimiento: date
    dias_restantes: int
    nivel: int
    etiqueta: Etiqueta
    fijada: bool
    orden_urgente: OrdenUrgenteBandeja | None
    en_proceso: EnProcesoBandeja | None
    comprobante_estado: str | None


class ContadoresBandeja(BaseModel):
    por_pagar: int
    por_validar: int
    rechazadas: int


class BandejaSalida(Pagina[ItemBandeja]):
    """Página de la pestaña pedida; total es su contador."""

    contadores: ContadoresBandeja
