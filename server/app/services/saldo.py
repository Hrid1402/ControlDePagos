"""Saldo de una deuda y consumo del mes del gerente: contratos comunes de H05, H14, H17, H22 y H36.

Saldo = monto confirmado menos la suma de monto_aplicado de los comprobantes validados. Los
comprobantes procesando, en revisión o rechazados no restan. Ninguno de los dos valores se guarda:
salen de consultas.

Vencida y la proyección de una deuda sin recibo también se definen aquí una sola vez, para que el
listado (H36), la bandeja (H15), el calendario (H16) y el panel (H14) cuenten lo mismo.

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
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    ColumnElement,
    ColumnExpressionArgument,
    Date,
    Interval,
    ScalarSelect,
    and_,
    case,
    cast,
    exists,
    func,
    literal,
    or_,
    select,
)
from sqlalchemy.orm import Session, aliased
from sqlalchemy.sql.selectable import LateralFromClause

from app.core.tiempo import ahora_lima, zona_horaria
from app.models import Comprobante, ComprobanteDeuda, Deuda, Usuario

MONEDA_LIMITE = "PEN"
# Estados en los que el saldo de la deuda está reservado por un intento de pago.
ESTADOS_RESERVA = ("en_proceso", "por_validar")
# Comprobantes que todavía pueden convertirse en abono.
ESTADOS_COMPROBANTE_ACTIVO = ("procesando", "en_revision", "por_confirmar")
# Deudas que ya no se cobran: no vencen ni cuentan como pendientes.
ESTADOS_CERRADOS = ("pagada", "anulada")


def aplicado_validado(deuda_id: ColumnExpressionArgument[uuid.UUID]) -> ScalarSelect[Decimal]:
    """Suma de abonos validados de la deuda. Usada con Deuda.id dentro de una consulta sobre
    deuda, queda correlacionada por fila."""
    # Cero con dos decimales, como numeric(12,2): sin abonos se lee 0.00, no 0.
    return (
        select(func.coalesce(func.sum(ComprobanteDeuda.monto_aplicado), Decimal("0.00")))
        .join(Comprobante, Comprobante.id == ComprobanteDeuda.comprobante_id)
        .where(ComprobanteDeuda.deuda_id == deuda_id, Comprobante.estado == "validado")
        .correlate_except(ComprobanteDeuda, Comprobante)
        .scalar_subquery()
    )


def abonos_validados() -> LateralFromClause:
    """aplicado_validado como columna aplicado de un LATERAL por deuda, para unirlo a una consulta
    sobre deuda. En un agregado que usa el abono dos veces (pagado y saldo) se evalúa una sola vez
    por fila; como subconsulta escalar repetida, PostgreSQL la ejecutaría dos veces. OFFSET 0 es
    la barrera que impide que PostgreSQL aplane el LATERAL y vuelva a repetirla."""
    return select(aplicado_validado(Deuda.id).label("aplicado")).offset(0).lateral("abonos")


def vencida(hoy: date) -> ColumnElement[bool]:
    """Vencida es un dato calculado, no un estado: el vencimiento es anterior a hoy en Lima y la
    deuda todavía se cobra (no está pagada ni anulada). Una deuda que vence hoy aún no está
    vencida. hoy llega como parámetro (hoy_de), no como CURRENT_DATE."""
    return and_(Deuda.fecha_vencimiento < hoy, Deuda.estado.not_in(ESTADOS_CERRADOS))


def proyeccion_sin_recibo() -> ColumnElement[Decimal | None]:
    """Estimación de una deuda sin monto (esperando recibo), regla de H14: el monto confirmado de la
    deuda del periodo anterior del mismo servicio, moneda y cuota, si no está anulada. Sin esa
    referencia es NULL y se muestra sin estimación, nunca como cero. Una deuda con monto no se
    proyecta. Busca por uq_deuda_periodo."""
    anterior = aliased(Deuda)
    mes_anterior = cast(Deuda.periodo - func.make_interval(0, 1, type_=Interval), Date)
    # Literales en la SQL, no parámetros: así coinciden con la expresión y el predicado del índice.
    sin_cuota = literal(0, literal_execute=True)
    monto_anterior = (
        select(anterior.monto)
        .where(
            anterior.servicio_id == Deuda.servicio_id,
            anterior.periodo == mes_anterior,
            func.coalesce(anterior.cuota_numero, sin_cuota)
            == func.coalesce(Deuda.cuota_numero, sin_cuota),
            anterior.estado != literal("anulada", literal_execute=True),
            anterior.moneda == Deuda.moneda,
        )
        .correlate(Deuda)
        .scalar_subquery()
    )
    return case((Deuda.monto.is_(None), monto_anterior), else_=None)


def aplicado_de(db: Session, deuda_id: uuid.UUID) -> Decimal:
    return db.scalar(select(aplicado_validado(Deuda.id)).where(Deuda.id == deuda_id)) or Decimal(0)


def saldo_de(db: Session, deuda: Deuda) -> Decimal | None:
    """Saldo pendiente de la deuda, o None si aún no tiene monto confirmado (esperando recibo):
    un saldo desconocido nunca se presenta como cero."""
    if deuda.monto is None:
        return None
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
