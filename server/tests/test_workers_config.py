from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from celery.schedules import crontab

from app.core.config import settings
from app.workers import celery_app as modulo_celery
from app.workers.base import BLOQUEO_SEGUNDOS, TareaBase
from app.workers.celery_app import COLA_GENERAL, celery_app
from app.workers.horarios import HORARIOS

conf = celery_app.conf


def test_usa_el_redis_de_la_configuracion_como_broker_y_backend() -> None:
    assert conf.broker_url == settings.redis_url
    assert conf.result_backend == settings.redis_url


def test_solo_acepta_mensajes_en_json() -> None:
    assert (conf.task_serializer, conf.result_serializer) == ("json", "json")
    assert conf.accept_content == ["json"]


def test_beat_lee_las_horas_en_la_zona_del_sistema() -> None:
    assert settings.timezone == "America/Lima"
    assert conf.timezone == settings.timezone
    assert conf.enable_utc is True
    assert celery_app.timezone == ZoneInfo("America/Lima")


def test_un_horario_diario_se_cumple_a_esa_hora_de_lima() -> None:
    lima = ZoneInfo("America/Lima")
    # 2026-10-21 04:00 UTC son las 23:00 del 20 en Lima: faltan 65 minutos para las 00:05.
    diario = crontab(
        hour=0, minute=5, app=celery_app, nowfun=lambda: datetime(2026, 10, 21, 4, 0, tzinfo=UTC)
    )
    assert diario.remaining_estimate(datetime(2026, 10, 20, 0, 5, tzinfo=lima)) == timedelta(
        hours=1, minutes=5
    )


def test_confirma_al_terminar_y_toma_un_mensaje_a_la_vez() -> None:
    assert conf.task_acks_late is True
    assert conf.task_reject_on_worker_lost is False
    assert conf.worker_prefetch_multiplier == 1


def test_limites_de_tiempo_y_resultados_por_defecto() -> None:
    assert conf.task_soft_time_limit < conf.task_time_limit
    assert conf.task_ignore_result is True
    assert conf.result_expires == timedelta(days=1)
    assert conf.task_default_queue == COLA_GENERAL


def test_los_encargos_programados_no_se_repiten_antes_de_una_hora() -> None:
    assert conf.broker_transport_options["visibility_timeout"] >= 3600


def test_las_tareas_usan_la_base_con_reintentos_limitados() -> None:
    assert issubclass(celery_app.Task, TareaBase)
    assert TareaBase.max_retries == 3
    assert TareaBase.retry_backoff == 5
    assert TareaBase.retry_backoff_max == 300
    assert TareaBase.retry_jitter is True
    assert TareaBase.acks_late is True


def test_el_bloqueo_dura_mas_que_el_limite_de_tiempo_de_una_tarea() -> None:
    assert conf.task_time_limit < BLOQUEO_SEGUNDOS


def test_cada_horario_apunta_a_una_tarea_registrada_y_vence_si_no_se_atiende() -> None:
    celery_app.loader.import_default_modules()
    assert conf.beat_schedule is HORARIOS
    assert HORARIOS
    for nombre, entrada in HORARIOS.items():
        assert entrada["task"] in celery_app.tasks, nombre
        assert entrada["options"]["expires"] > 0, nombre


def test_el_latido_corre_cada_cinco_minutos() -> None:
    assert HORARIOS["latido"]["schedule"] == crontab(minute="*/5")


def test_cada_proceso_del_worker_abre_sus_propias_conexiones(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    llamadas: list[bool] = []
    monkeypatch.setattr(modulo_celery.engine, "dispose", lambda close=True: llamadas.append(close))
    modulo_celery.descartar_conexiones_heredadas()
    assert llamadas == [False]
