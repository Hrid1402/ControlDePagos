"""Hora oficial del sistema: la zona de settings.timezone (America/Lima por defecto).

Las fechas se guardan en UTC y los cortes de día y de mes se calculan en esta zona.
"""

from datetime import datetime
from zoneinfo import ZoneInfo

from app.core.config import settings


def zona_horaria() -> ZoneInfo:
    return ZoneInfo(settings.timezone)


def ahora_lima() -> datetime:
    return datetime.now(zona_horaria())
