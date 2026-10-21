"""Hora oficial del sistema: la zona de settings.timezone (America/Lima por defecto).

Las fechas se guardan en UTC y los cortes de día y de mes se calculan en esta zona.
"""

import calendar
from datetime import date, datetime
from zoneinfo import ZoneInfo

from app.core.config import settings


def zona_horaria() -> ZoneInfo:
    return ZoneInfo(settings.timezone)


def ahora_lima() -> datetime:
    return datetime.now(zona_horaria())


def hoy_de(ahora: datetime) -> date:
    """Fecha de ahora en la zona del sistema. Se calcula aquí y llega a SQL como parámetro: la base
    guarda UTC y su CURRENT_DATE no es la fecha de Lima por la noche."""
    return ahora.astimezone(zona_horaria()).date()


def dia_del_mes(anio: int, mes: int, dia: int) -> date:
    """El día pedido del mes; si el mes no lo tiene (31 en febrero), el último día del mes."""
    return date(anio, mes, min(dia, calendar.monthrange(anio, mes)[1]))


def sumar_meses(fecha: date, meses: int, dia: int | None = None) -> date:
    """La fecha meses después, el mismo día (o dia) ajustado al último día del mes de destino."""
    indice = fecha.year * 12 + fecha.month - 1 + meses
    return dia_del_mes(indice // 12, indice % 12 + 1, dia or fecha.day)
