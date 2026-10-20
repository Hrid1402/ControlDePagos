"""Encolar tareas de Celery solo si la transacción se confirma.

Un servicio que pide trabajo en segundo plano llama a encolar_tras_commit en su misma sesión con la
firma de la tarea, por ejemplo tarea.s(str(comprobante.id)). Si la transacción se deshace, no se
encola nada. Los argumentos van en JSON: ids como texto, nunca objetos del ORM.

Encolar ocurre después del commit y no puede deshacerlo: si Redis no responde, se registra en el
log y se sigue. Por eso todo trabajo encolado así deja en la base un estado que un job de Beat
recorre para volver a encolarlo (por ejemplo, un comprobante en procesando sin resultado), y la
tarea es idempotente ante ese segundo envío.
"""

import logging

import redis
from celery.canvas import Signature
from celery.exceptions import OperationalError as ErrorBroker
from sqlalchemy.orm import Session

from app.core.eventos import ejecutar_tras_commit

logger = logging.getLogger("app.workers")


def encolar(firma: Signature) -> bool:
    """Envía la tarea al broker. Devuelve False si no se pudo; no registra sus argumentos."""
    try:
        firma.apply_async()
    except (ErrorBroker, redis.RedisError):
        logger.warning(
            "No se pudo encolar la tarea %s; la recuperará su revisión programada",
            firma.task,
            exc_info=True,
        )
        return False
    return True


def encolar_tras_commit(db: Session, firma: Signature) -> None:
    """Encola la tarea solo si la transacción de db se confirma."""
    ejecutar_tras_commit(db, lambda: encolar(firma))
