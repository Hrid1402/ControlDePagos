"""Recordatorios de solicitudes de aprobación pendientes (H05 CA09, TASK-24).

Cada 15 minutos revisa las solicitudes pendientes: recuerda al gerente cada turno de 2 horas sin
respuesta y, el día en que la deuda vence, avisa de inmediato y como urgente. Al aprobar o
rechazar, la solicitud deja de estar pendiente y no se recuerda más. Cada aviso lleva su turno o
su día en clave_evento, así que repetir el job no lo duplica (app/services/limites.py).
"""

from app.core.tiempo import ahora_lima
from app.services.limites import recordar_pendientes
from app.workers.base import sesion_de_trabajo, un_solo_a_la_vez
from app.workers.celery_app import celery_app

BLOQUEO_APROBACIONES = "recordar_aprobaciones"


@celery_app.task
def recordar_aprobaciones() -> int | None:
    """Devuelve cuántos recordatorios envió, o None si otra ejecución tenía el bloqueo."""
    with un_solo_a_la_vez(BLOQUEO_APROBACIONES) as tomado:
        if not tomado:
            return None
        with sesion_de_trabajo() as db:
            return recordar_pendientes(db, ahora_lima())
