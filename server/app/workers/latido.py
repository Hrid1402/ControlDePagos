"""Latido: comprueba cada 5 minutos que Beat, el worker, la base y Redis responden.

Guarda en Redis, en control_pagos:latido, la hora de Lima de la última ejecución y la hora que
devolvió la base. La clave vence a los 15 minutos: si no existe, el worker o Beat están detenidos.

    docker compose exec redis redis-cli GET control_pagos:latido

No cambia datos de negocio y repetirlo solo reemplaza el registro.
"""

import json

from sqlalchemy import func, select

from app.core.eventos import cliente_redis
from app.core.tiempo import ahora_lima, zona_horaria
from app.workers.base import sesion_de_trabajo, un_solo_a_la_vez
from app.workers.celery_app import celery_app

CLAVE_LATIDO = "control_pagos:latido"
BLOQUEO_LATIDO = "latido"
VIGENCIA_SEGUNDOS = 15 * 60


@celery_app.task(soft_time_limit=20, time_limit=30)
def latido() -> dict[str, str] | None:
    """Devuelve el registro guardado, o None si otra ejecución tenía el bloqueo."""
    with un_solo_a_la_vez(BLOQUEO_LATIDO) as tomado:
        if not tomado:
            return None
        with sesion_de_trabajo() as db:
            hora_base = db.execute(select(func.now())).scalar_one()
        registro = {
            "ejecutado_en": ahora_lima().isoformat(),
            "hora_base": hora_base.astimezone(zona_horaria()).isoformat(),
        }
        cliente_redis().set(CLAVE_LATIDO, json.dumps(registro), ex=VIGENCIA_SEGUNDOS)
        return registro
