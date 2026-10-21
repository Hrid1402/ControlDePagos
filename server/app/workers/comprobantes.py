"""Validación automática de comprobantes en la cola ocr (H24 CA03, TASK-85).

procesar_comprobante lee el archivo de S3, hace el OCR fuera de toda transacción y aplica el
resultado con el comprobante bloqueado (app/services/validacion.py). La subida la encola tras su
commit; si Redis no respondía, o el worker murió a mitad, recuperar_comprobantes la vuelve a
encolar.

- Cola ocr con un proceso por worker: el modelo ocupa cerca de 1 GB y se precarga al iniciar.
- Límite de LIMITE_SUAVE segundos por lectura. Un fallo de lectura (timeout, archivo que no se
  convierte, S3 caído) se reintenta hasta MAXIMO_REINTENTOS veces con espera creciente; agotados,
  el comprobante queda en revisión del gerente con la explicación.
- Idempotente: si el comprobante ya no está en procesando, la tarea termina sin efectos.
"""

import logging
import uuid
from datetime import timedelta

from celery import Task
from celery.exceptions import SoftTimeLimitExceeded
from sqlalchemy import select

from app.core.errores import ErrorApi
from app.core.tiempo import ahora_lima
from app.models import Comprobante
from app.ocr.motor import ErrorOcr, LecturaOcr, leer_documento
from app.services.archivos import leer_privado
from app.services.validacion import aplicar_lectura, bloquear_comprobante, sin_lectura
from app.workers.base import sesion_de_trabajo, un_solo_a_la_vez
from app.workers.celery_app import COLA_OCR, TAREA_PROCESAR_COMPROBANTE, celery_app
from app.workers.encolar import encolar

logger = logging.getLogger("app.workers")

LIMITE_SUAVE = 45
LIMITE_DURO = 60
MAXIMO_REINTENTOS = 2
ESPERA_REINTENTO_SEGUNDOS = 10

BLOQUEO_RECUPERAR = "recuperar_comprobantes"
# Un comprobante en procesando sin cambios en este tiempo perdió su tarea: se vuelve a encolar.
ESPERA_RECUPERAR = timedelta(minutes=10)
MAXIMO_RECUPERACIONES = 3
LOTE_RECUPERAR = 100

FALLOS_DE_LECTURA = (ErrorOcr, SoftTimeLimitExceeded)


def leer(comprobante_id: uuid.UUID) -> tuple[str, str] | None:
    """Ruta y tipo del archivo si el comprobante sigue en procesando."""
    with sesion_de_trabajo() as db:
        comprobante = db.get(Comprobante, comprobante_id)
        if comprobante is None or comprobante.estado != "procesando":
            return None
        return comprobante.archivo_url, comprobante.archivo_tipo


@celery_app.task(
    bind=True,
    name=TAREA_PROCESAR_COMPROBANTE,
    queue=COLA_OCR,
    soft_time_limit=LIMITE_SUAVE,
    time_limit=LIMITE_DURO,
)
def procesar_comprobante(self: Task, comprobante_id: str) -> str | None:
    """Devuelve el estado aplicado, o None si el comprobante ya estaba resuelto."""
    identificador = uuid.UUID(comprobante_id)
    archivo = leer(identificador)
    if archivo is None:
        return None
    ruta, extension = archivo
    try:
        lectura: LecturaOcr | None = leer_documento(leer_privado(ruta), extension)
    except (*FALLOS_DE_LECTURA, ErrorApi) as error:
        if self.request.retries < MAXIMO_REINTENTOS:
            espera = ESPERA_REINTENTO_SEGUNDOS * 2**self.request.retries
            raise self.retry(exc=error, countdown=espera, max_retries=MAXIMO_REINTENTOS) from error
        logger.warning("No se pudo leer el comprobante %s", comprobante_id, exc_info=True)
        lectura = None
    with sesion_de_trabajo() as db:
        comprobante = bloquear_comprobante(db, identificador)
        if comprobante is None:
            return None
        aplicado = (
            aplicar_lectura(db, comprobante, lectura)
            if lectura is not None
            else sin_lectura(db, comprobante)
        )
        return comprobante.estado if aplicado else None


@celery_app.task(soft_time_limit=50, time_limit=60)
def recuperar_comprobantes() -> int | None:
    """Vuelve a encolar los comprobantes en procesando que llevan ESPERA_RECUPERAR sin cambios.
    Tras MAXIMO_RECUPERACIONES los deja en revisión. Devuelve cuántos atendió, o None si otra
    ejecución tenía el bloqueo."""
    with un_solo_a_la_vez(BLOQUEO_RECUPERAR) as tomado:
        if not tomado:
            return None
        limite = ahora_lima() - ESPERA_RECUPERAR
        with sesion_de_trabajo() as db:
            ids = list(
                db.scalars(
                    select(Comprobante.id)
                    .where(Comprobante.estado == "procesando", Comprobante.actualizado_en < limite)
                    .order_by(Comprobante.actualizado_en)
                    .limit(LOTE_RECUPERAR)
                )
            )
        for comprobante_id in ids:
            with sesion_de_trabajo() as db:
                comprobante = bloquear_comprobante(db, comprobante_id)
                if comprobante is None or comprobante.estado != "procesando":
                    continue
                veces = int(comprobante.datos_extraidos.get("recuperaciones", 0))
                if veces >= MAXIMO_RECUPERACIONES:
                    sin_lectura(db, comprobante)
                    continue
                # Contar la recuperación también renueva actualizado_en: no se vuelve a encolar
                # hasta que pase otra espera completa.
                comprobante.datos_extraidos = {
                    **comprobante.datos_extraidos,
                    "recuperaciones": veces + 1,
                }
            encolar(procesar_comprobante.s(str(comprobante_id)))
        return len(ids)
