"""Tarea diaria de deudas recurrentes y recibos retrasados (H11 CA04 y CA05, TASK-39).

Beat la encola a las 00:05 de Lima. Crea las deudas del día de las recurrencias activas, recupera
los días que el worker no corrió y avisa de los recibos que no llegan; las reglas están en
app/services/recurrencias.py. Repetirla no duplica deudas ni avisos.
"""

from app.core.tiempo import ahora_lima
from app.services.recurrencias import avisar_recibos_retrasados, generar_recurrentes
from app.workers.base import sesion_de_trabajo, un_solo_a_la_vez
from app.workers.celery_app import celery_app

BLOQUEO_RECURRENTES = "deudas_recurrentes"


@celery_app.task(soft_time_limit=50, time_limit=60)
def deudas_recurrentes() -> dict[str, int] | None:
    """Devuelve cuántas deudas creó y cuántos avisos envió, o None si otra ejecución corría."""
    with un_solo_a_la_vez(BLOQUEO_RECURRENTES) as tomado:
        if not tomado:
            return None
        ahora = ahora_lima()
        with sesion_de_trabajo() as db:
            creadas = generar_recurrentes(db, ahora)
            avisos = avisar_recibos_retrasados(db, ahora)
        return {"creadas": creadas, "avisos": avisos}
