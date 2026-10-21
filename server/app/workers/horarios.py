"""Horarios de Beat.

Cada tarea programada agrega aquí su entrada y su módulo al include de app/workers/celery_app.py.
Las horas de crontab se leen en la zona de settings.timezone (America/Lima). Ejemplos:
crontab(hour=0, minute=5) cada día a las 00:05 y crontab(minute="*/15") cada 15 minutos.

Beat corre en una sola instancia y solo encola: la tarea comprueba el estado actual al ejecutarse,
es idempotente y usa un_solo_a_la_vez para no pisarse con otra ejecución. Con options.expires, un
encargo que esperó en la cola más que su intervalo (por ejemplo, con el worker detenido) se
descarta en lugar de acumularse; la ejecución siguiente recupera lo pendiente.
"""

from typing import Any

from celery.schedules import crontab

HORARIOS: dict[str, dict[str, Any]] = {
    "latido": {
        "task": "app.workers.latido.latido",
        "schedule": crontab(minute="*/5"),
        "options": {"expires": 4 * 60},
    },
    "recuperar_comprobantes": {
        "task": "app.workers.comprobantes.recuperar_comprobantes",
        "schedule": crontab(minute="*/5"),
        "options": {"expires": 4 * 60},
    },
    "recordar_aprobaciones": {
        "task": "app.workers.aprobaciones.recordar_aprobaciones",
        "schedule": crontab(minute="*/15"),
        "options": {"expires": 14 * 60},
    },
}
