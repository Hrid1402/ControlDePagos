"""Saldo de una deuda y consumo del mes del gerente: contratos comunes de H05, H14, H17, H22 y H36.

Saldo = monto confirmado menos la suma de monto_aplicado de los comprobantes validados. Los
comprobantes procesando, en revisión o rechazados no restan. Ninguno de los dos valores se guarda:
salen de consultas.

Consumo PEN del mes de un gerente (límites de H05):
- Abonos: monto_aplicado de comprobantes validados que subió una asistente del gerente, incluidas
  las anteriores, en deudas PEN.
- Reservas: saldo de las deudas PEN en proceso o por validar cuyo intento inició una asistente.
Lo reservado que pasa a abono no se cuenta dos veces: el saldo ya descuenta lo validado y, al
validarse el pago, la deuda sale de los estados de reserva. USD no se suma: no hay conversión.
El consumo es del gerente, no de la asistente: un cambio de asistente no lo reinicia.

Fecha del abono: comprobante_deuda no tiene estado ni fecha de validación; su fila se crea al
subir el comprobante, porque el reparto entre deudas se confirma antes de validar (H24). Por eso
el mes del abono se toma de comprobante.creado_en, la fecha de subida, que no depende del OCR.
Un comprobante subido el 31 y validado el 1 cuenta en el mes de subida. TASK-87 debe revisar este
punto: si registra la fecha de validación (revisado_en también en la validación automática),
el filtro de consumo_mes_pen debe pasar a esa fecha.
"""

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import ColumnExpressionArgument, ScalarSelect, exists, func, or_, select
from sqlalchemy.orm import Session

from app.core.tiempo import ahora_lima, zona_horaria
from app.models import Comprobante, ComprobanteDeuda, Deuda, Usuario

MONEDA_LIMITE = "PEN"
# Estados en los que el saldo de la deuda está reservado por un intento de pago.
ESTADOS_RESERVA = ("en_proceso", "por_validar")
# Comprobantes que todavía pueden convertirse en abono.
ESTADOS_COMPROBANTE_ACTIVO = ("procesando", "en_revision", "por_confirmar")


def aplicado_validado(deuda_id: ColumnExpressionArgument[uuid.UUID]) -> ScalarSelect[Decimal]:
    """Suma de abonos validados de la deuda. Usada con Deuda.id dentro de una consulta sobre
    deuda, queda correlacionada por fila."""
    return (
        select(func.coalesce(func.sum(ComprobanteDeuda.monto_aplicado), 0))
        .join(Comprobante, Comprobante.id == ComprobanteDeuda.comprobante_id)
        .where(ComprobanteDeuda.deuda_id == deuda_id, Comprobante.estado == "validado")
        .correlate_except(ComprobanteDeuda, Comprobante)
        .scalar_subquery()
    )


def aplicado_de(db: Session, deuda_id: uuid.UUID) -> Decimal:
    return db.scalar(select(aplicado_validado(Deuda.id)).where(Deuda.id == deuda_id)) or Decimal(0)


def saldo_de(db: Session, deuda: Deuda) -> Decimal:
    """Saldo pendiente de la deuda. Sin monto confirmado (esperando recibo) no hay saldo."""
    if deuda.monto is None:
        return Decimal(0)
    return deuda.monto - aplicado_de(db, deuda.id)


def rango_mes(ahora: datetime) -> tuple[datetime, datetime]:
    """Inicio del mes de ahora y del siguiente, a las 00:00 de la zona del sistema."""
    local = ahora.astimezone(zona_horaria())
    inicio = local.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if inicio.month == 12:
        return inicio, inicio.replace(year=inicio.year + 1, month=1)
    return inicio, inicio.replace(month=inicio.month + 1)


def consumo_mes_pen(db: Session, gerente_id: uuid.UUID, ahora: datetime | None = None) -> Decimal:
    """Consumo PEN del mes del gerente frente a su límite mensual: abonos más reservas."""
    inicio, fin = rango_mes(ahora or ahora_lima())
    abonos = db.scalar(
        select(func.coalesce(func.sum(ComprobanteDeuda.monto_aplicado), 0))
        .join(Comprobante, Comprobante.id == ComprobanteDeuda.comprobante_id)
        .join(Deuda, Deuda.id == ComprobanteDeuda.deuda_id)
        .join(Usuario, Usuario.id == Comprobante.subido_por)
        .where(
            Deuda.gerente_id == gerente_id,
            Deuda.moneda == MONEDA_LIMITE,
            Comprobante.estado == "validado",
            Usuario.rol == "asistente",
            Comprobante.creado_en >= inicio,
            Comprobante.creado_en < fin,
        )
    )
    reservas = db.scalar(
        select(func.coalesce(func.sum(Deuda.monto - aplicado_validado(Deuda.id)), 0))
        .join(Usuario, Usuario.id == Deuda.pago_iniciado_por)
        .where(
            Deuda.gerente_id == gerente_id,
            Deuda.moneda == MONEDA_LIMITE,
            Deuda.estado.in_(ESTADOS_RESERVA),
            Usuario.rol == "asistente",
        )
    )
    return (abonos or Decimal(0)) + (reservas or Decimal(0))


def tiene_comprobante_activo(db: Session, deuda_id: uuid.UUID) -> bool:
    """Si la deuda tiene un comprobante que aún puede validarse, por reparto o por sugerencia."""
    asociado = exists().where(
        ComprobanteDeuda.comprobante_id == Comprobante.id, ComprobanteDeuda.deuda_id == deuda_id
    )
    return bool(
        db.scalar(
            select(
                exists().where(
                    Comprobante.estado.in_(ESTADOS_COMPROBANTE_ACTIVO),
                    or_(asociado, Comprobante.deuda_sugerida_id == deuda_id),
                )
            )
        )
    )
