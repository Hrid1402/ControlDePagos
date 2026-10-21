"""App de Celery: worker y planificador Beat sobre el Redis de settings.redis_url.

Arranque local, desde la raíz del repositorio: pnpm worker:server y pnpm beat:server, o pnpm dev,
que los arranca junto con el client y el server. Ver server/README.md.

- Mensajes solo en JSON. Las horas de Beat se leen en settings.timezone (America/Lima); Celery
  trabaja internamente en UTC.
- El mensaje se confirma al terminar la tarea (acks tardíos) y cada proceso toma uno a la vez. Si
  el proceso muere a mitad de una tarea, esta no se reencola sola: la recupera su job de Beat.
- Límite de tiempo por defecto de 60 s (aviso) y 90 s (corte); cada tarea puede fijar los suyos.
- Los resultados se ignoran salvo que la tarea o el envío pidan guardarlos: el estado de cada
  proceso vive en la base y llega al cliente por la API y el WebSocket.
- Dos colas: general (jobs de Beat y avisos) y ocr (lectura de comprobantes, con su propio worker
  para que una lectura lenta no retrase los recordatorios).
- Un encargo programado (eta o countdown) no puede superar visibility_timeout: pasado ese tiempo
  sin confirmarse, Redis lo entrega otra vez. Para plazos largos se usa una revisión de Beat.
"""

from datetime import timedelta
from typing import Any

from celery import Celery
from celery.signals import worker_process_init

# eventos registra los listeners de la sesión que publican eventos y encolan tareas tras commit.
from app.core import eventos  # noqa: F401
from app.core.config import settings
from app.core.database import engine
from app.workers.horarios import HORARIOS

COLA_GENERAL = "general"
# OCR de comprobantes: worker propio con un proceso y el modelo precargado (pnpm worker:ocr).
COLA_OCR = "ocr"
TAREA_PROCESAR_COMPROBANTE = "app.workers.comprobantes.procesar_comprobante"
ESPERA_REDIS_SEGUNDOS = 2
VISIBILIDAD_SEGUNDOS = 3600

celery_app = Celery(
    "control_pagos",
    broker=settings.redis_url,
    backend=settings.redis_url,
    task_cls="app.workers.base:TareaBase",
    include=[
        "app.workers.aprobaciones",
        "app.workers.comprobantes",
        "app.workers.latido",
        "app.workers.recurrencias",
    ],
)
celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone=settings.timezone,
    enable_utc=True,
    task_default_queue=COLA_GENERAL,
    # Quien encola por nombre (celery_app.signature) no necesita importar la tarea ni el OCR.
    task_routes={TAREA_PROCESAR_COMPROBANTE: {"queue": COLA_OCR}},
    task_acks_late=True,
    task_reject_on_worker_lost=False,
    worker_prefetch_multiplier=1,
    task_soft_time_limit=60,
    task_time_limit=90,
    task_ignore_result=True,
    result_expires=timedelta(days=1),
    redis_socket_connect_timeout=ESPERA_REDIS_SEGUNDOS,
    redis_socket_timeout=ESPERA_REDIS_SEGUNDOS,
    broker_connection_retry_on_startup=True,
    broker_transport_options={
        "visibility_timeout": VISIBILIDAD_SEGUNDOS,
        "socket_connect_timeout": ESPERA_REDIS_SEGUNDOS,
    },
    # Encolar ocurre tras el commit de una petición: si Redis no responde, se reintenta una vez y
    # se informa el fallo en lugar de dejar la petición esperando.
    task_publish_retry_policy={
        "max_retries": 1,
        "interval_start": 0,
        "interval_step": 0.5,
        "interval_max": 0.5,
    },
    beat_schedule=HORARIOS,
)


@worker_process_init.connect
def descartar_conexiones_heredadas(**_: Any) -> None:
    # Cada proceso hijo del worker abre sus propias conexiones a la base: las del pool que heredó
    # del proceso padre al crearse no se comparten entre procesos.
    engine.dispose(close=False)
    if settings.ocr_precargar:
        from app.ocr.motor import precargar

        precargar()
