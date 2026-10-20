"""Base común de las tareas de Celery: reintentos limitados, sesión propia y bloqueo.

Toda tarea de celery_app usa TareaBase. Solo se reintentan los fallos transitorios de la base o de
Redis, con espera creciente y un máximo de intentos; un error de lógica falla sin reintentar.

Patrón de un job:
1. Si lo dispara Beat, tomar el bloqueo con un_solo_a_la_vez; si otra ejecución lo tiene, terminar.
2. Abrir sesion_de_trabajo: una sesión propia por ejecución que confirma al salir.
3. Elegir los candidatos por su estado actual y volver a comprobarlo dentro de la transacción.
4. Aplicar efectos idempotentes: notificar con clave_evento, actualizar con la condición de estado
   y apoyarse en las unicidades de la base. Repetir el job no debe duplicar nada.
5. Eventos con publicar_tras_commit o notificar, y tareas derivadas con encolar_tras_commit: salen
   solo si la sesión confirma.
"""

import logging
from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager, contextmanager

import redis
from celery import Task
from celery.exceptions import OperationalError as ErrorBroker
from sqlalchemy.exc import OperationalError as ErrorBaseDatos
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.core.eventos import cliente_redis

logger = logging.getLogger("app.workers")

ERRORES_TRANSITORIOS: tuple[type[Exception], ...] = (ErrorBaseDatos, redis.RedisError, ErrorBroker)
MAXIMO_REINTENTOS = 3
ESPERA_INICIAL_SEGUNDOS = 5
ESPERA_MAXIMA_SEGUNDOS = 300

PREFIJO_BLOQUEO = "control_pagos:bloqueo:"
# Mayor que task_time_limit: si el worker muere a mitad del job, el bloqueo expira solo.
BLOQUEO_SEGUNDOS = 120

Fabrica = Callable[[], AbstractContextManager[Session]]

# Las tareas abren sus sesiones con la misma configuración que la API. Las pruebas la reemplazan.
fabrica_sesiones: Fabrica = SessionLocal


class TareaBase(Task):
    """Reintentos limitados con espera creciente (5 s, 10 s, 20 s... hasta 300 s, con variación
    aleatoria) y confirmación del mensaje al terminar la tarea, no al recibirla."""

    autoretry_for = ERRORES_TRANSITORIOS
    max_retries = MAXIMO_REINTENTOS
    retry_backoff = ESPERA_INICIAL_SEGUNDOS
    retry_backoff_max = ESPERA_MAXIMA_SEGUNDOS
    retry_jitter = True
    acks_late = True


@contextmanager
def sesion_de_trabajo() -> Iterator[Session]:
    """Sesión propia de una ejecución: confirma al salir sin errores y deshace si hay una
    excepción, con lo que se descartan los eventos y tareas encolados tras commit."""
    with fabrica_sesiones() as db:
        try:
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise


@contextmanager
def un_solo_a_la_vez(nombre: str, segundos: int = BLOQUEO_SEGUNDOS) -> Iterator[bool]:
    """Bloqueo en Redis para que un job no corra dos veces a la vez. Entrega False si otra
    ejecución lo tiene, y el job termina sin hacer nada. Si Redis no responde, lanza
    redis.RedisError y la tarea se reintenta."""
    bloqueo = cliente_redis().lock(PREFIJO_BLOQUEO + nombre, timeout=segundos, blocking=False)
    if not bloqueo.acquire():
        logger.info("Se omitió %s: otra ejecución tiene el bloqueo", nombre)
        yield False
        return
    try:
        yield True
    finally:
        try:
            bloqueo.release()
        except redis.exceptions.LockError:
            logger.warning("El bloqueo de %s expiró antes de terminar el job", nombre)
