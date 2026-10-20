"""Esquemas del registro manual (H11, TASK-38) y del listado de deudas (H36, TASK-45).

El periodo viaja como AAAA-MM y se guarda como el primer día de ese mes (ck_deuda_periodo).
Aquí no se reciben fecha de emisión, campos de tarjeta o de préstamo (TASK-40) ni el recibo
adjunto (TASK-84). Tampoco estado ni origen: el registro manual siempre crea una deuda pendiente.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal, get_args

from pydantic import BaseModel, Field, StringConstraints, field_validator

from app.core.paginacion import Pagina
from app.schemas.bandeja import CategoriaBandeja

Moneda = Literal["PEN", "USD"]
MONEDAS: tuple[Moneda, ...] = get_args(Moneda)
# Los estados de ck_deuda_estado en el orden de su ciclo de vida, que es el orden por estado.
EstadoDeuda = Literal[
    "esperando_recibo",
    "pendiente",
    "esperando_aprobacion",
    "en_proceso",
    "por_validar",
    "con_problema",
    "pagada_parcial",
    "pagada",
    "anulada",
]
ESTADOS_DEUDA: tuple[EstadoDeuda, ...] = get_args(EstadoDeuda)
# Sin guion, ascendente; con guion, descendente.
OrdenListado = Literal["vencimiento", "-vencimiento", "monto", "-monto", "estado", "-estado"]
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


class ItemDeuda(BaseModel):
    """Fila del listado (CA01). pagado, saldo, vencida y monto_proyectado son calculados. Sin monto
    (esperando recibo), monto y saldo son null y la estimación va en monto_proyectado, que es null
    si no hay deuda del mes anterior para estimarla."""

    id: uuid.UUID
    servicio_id: uuid.UUID
    empresa: str
    alias: str | None
    codigo_suministro: str
    categoria: CategoriaBandeja
    periodo: str
    monto: Decimal | None
    moneda: str
    pagado: Decimal
    saldo: Decimal | None
    monto_proyectado: Decimal | None
    fecha_vencimiento: date
    vencida: bool
    estado: str
    numero_recibo: str | None


CERO = Decimal("0.00")


class TotalesMoneda(BaseModel):
    """Totales de una moneda sobre todo el filtro, no solo la página (CA08). monto es el importe
    confirmado; pagado, los abonos validados; saldo, monto menos abonos. Las deudas sin monto no
    suman a ninguno: se cuentan en sin_monto y su estimación va en proyectado, o en
    sin_estimacion si no la tienen."""

    cantidad: int = 0
    monto: Decimal = CERO
    pagado: Decimal = CERO
    saldo: Decimal = CERO
    sin_monto: int = 0
    proyectado: Decimal = CERO
    sin_estimacion: int = 0


class ListadoDeudasSalida(Pagina[ItemDeuda]):
    """Página del listado. totales trae siempre PEN y USD, separados: no se convierten ni suman."""

    totales: dict[Moneda, TotalesMoneda]
