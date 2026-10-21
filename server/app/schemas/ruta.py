import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from app.schemas.bandeja import CategoriaBandeja
from app.services.ruta import MAXIMO_LOTE, ResultadoLote


class TotalesRuta(BaseModel):
    """Lo que hay que llevar, por moneda: soles y dólares no se suman."""

    PEN: Decimal
    USD: Decimal


class ItemRuta(BaseModel):
    """Una deuda de la ruta. en_ruta: la persona ya la tiene en proceso. pago_realizado: declaró
    el pago, pero la deuda sigue por validar hasta que se valide su comprobante."""

    id: uuid.UUID
    empresa: str | None
    alias: str | None
    codigo_suministro: str
    categoria: CategoriaBandeja
    monto: Decimal
    saldo: Decimal
    moneda: str
    estado: str
    fecha_vencimiento: date
    en_ruta: bool
    pago_realizado: bool
    pago_realizado_en: datetime | None
    comprobante_estado: str | None


class GrupoRutaSalida(BaseModel):
    """lugar es null para las deudas cuyo servicio no tiene lugar de pago registrado."""

    lugar: str | None
    items: list[ItemRuta]
    totales: TotalesRuta


class RutaSalida(BaseModel):
    grupos: list[GrupoRutaSalida]
    totales: TotalesRuta


class IniciarRutaEntrada(BaseModel):
    deudas: list[uuid.UUID] = Field(min_length=1, max_length=MAXIMO_LOTE)


class ResultadoDeudaSalida(BaseModel):
    """iniciada o requiere_aprobacion vienen de iniciar_pago; conflicto trae el código y el
    mensaje del 404 o 409 que habría respondido esa deuda sola."""

    deuda_id: uuid.UUID
    resultado: ResultadoLote
    codigo: str | None
    mensaje: str | None
    repetido: bool


class IniciarRutaSalida(BaseModel):
    resultados: list[ResultadoDeudaSalida]
    # Total por lo que sí se inició: lo que hay que llevar en esta salida.
    totales: TotalesRuta
