"""Detalle de una deuda (H17, TASK-53)."""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel

from app.schemas.bandeja import CategoriaBandeja, EnProcesoBandeja, OrdenUrgenteBandeja


class ServicioDetalle(BaseModel):
    id: uuid.UUID
    empresa: str
    alias: str | None
    codigo_suministro: str
    titular: str | None
    lugar_pago: str | None
    notas: str | None


class ComprobanteDeLaDeuda(BaseModel):
    """Comprobante que cubre la deuda, con el resultado de su validación (CA03). monto_aplicado
    es lo que este comprobante cubre de esta deuda; solo los validados son abonos (CA09)."""

    id: uuid.UUID
    estado: str
    motivo_codigo: str | None
    observacion: str | None
    monto: Decimal | None
    monto_aplicado: Decimal
    moneda: str
    subido_por: str
    creado_en: datetime
    reemplaza_a_id: uuid.UUID | None


class CambioMonto(BaseModel):
    monto_anterior: Decimal
    monto_nuevo: Decimal
    origen: str
    usuario: str | None
    creado_en: datetime


class Actor(BaseModel):
    nombre: str
    rol: str | None


class EventoDeuda(BaseModel):
    """Un hecho de la línea de tiempo (CA04). tipo es la acción auditada o un resultado del
    comprobante; el texto lo pone el cliente. actor None: lo hizo el sistema."""

    tipo: str
    fecha: datetime
    actor: Actor | None
    detalle: dict[str, Any]


class DetalleDeudaSalida(BaseModel):
    id: uuid.UUID
    servicio: ServicioDetalle
    categoria: CategoriaBandeja
    periodo: str
    estado: str
    origen: str
    moneda: str
    monto: Decimal | None
    pagado: Decimal
    saldo: Decimal | None
    monto_proyectado: Decimal | None
    vencida: bool
    fecha_emision: date | None
    fecha_vencimiento: date
    fecha_estimada: date | None
    fecha_corte: date | None
    pago_minimo: Decimal | None
    pago_total: Decimal | None
    numero_recibo: str | None
    # Enlace firmado de 5 minutos para ver o descargar el recibo (CA02).
    recibo_enlace: str | None
    cuota_numero: int | None
    cuotas_total: int | None
    en_proceso: EnProcesoBandeja | None
    orden_urgente: OrdenUrgenteBandeja | None
    creado_en: datetime
    comprobantes: list[ComprobanteDeLaDeuda]
    historial_montos: list[CambioMonto]
    linea_tiempo: list[EventoDeuda]
    # Lo que el usuario puede hacer ahora; el cliente solo muestra estas (CA07, CA08).
    acciones: list[str]
