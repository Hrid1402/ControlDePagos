import logging
import uuid
from collections.abc import Iterator
from contextlib import nullcontext

import pytest
import redis
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.core.eventos import Evento, TipoEvento, cliente_redis, publicar_tras_commit
from app.workers import base
from app.workers.base import (
    BLOQUEO_SEGUNDOS,
    PREFIJO_BLOQUEO,
    sesion_de_trabajo,
    un_solo_a_la_vez,
)
from app.workers.celery_app import celery_app
from tests.conftest import DosGerentes

Publicados = list[tuple[uuid.UUID, Evento]]

llamadas: list[str] = []


def error_de_base() -> OperationalError:
    return OperationalError("SELECT 1", {}, Exception("la base no responde"))


@celery_app.task(name="pruebas.falla_con_la_base")
def falla_con_la_base(fallos: int) -> int:
    llamadas.append("base")
    if len(llamadas) <= fallos:
        raise error_de_base()
    return len(llamadas)


@celery_app.task(name="pruebas.falla_con_redis")
def falla_con_redis(fallos: int) -> int:
    llamadas.append("redis")
    if len(llamadas) <= fallos:
        raise redis.ConnectionError("Redis no responde")
    return len(llamadas)


@celery_app.task(name="pruebas.falla_por_logica")
def falla_por_logica() -> None:
    llamadas.append("logica")
    raise ValueError("dato inválido")


@pytest.fixture(autouse=True)
def sin_llamadas() -> None:
    llamadas.clear()


@pytest.fixture
def sesion_de_prueba(db: Session, monkeypatch: pytest.MonkeyPatch) -> Session:
    """El job usa la sesión de la prueba, que se deshace al terminar."""
    monkeypatch.setattr(base, "fabrica_sesiones", lambda: nullcontext(db))
    return db


@pytest.fixture
def nombre_bloqueo() -> Iterator[str]:
    nombre = f"pruebas-{uuid.uuid4().hex}"
    try:
        yield nombre
    finally:
        cliente_redis().delete(PREFIJO_BLOQUEO + nombre)


def test_un_fallo_transitorio_de_la_base_se_reintenta_hasta_funcionar() -> None:
    resultado = falla_con_la_base.apply(args=(2,))
    assert resultado.get() == 3
    assert llamadas == ["base"] * 3


def test_un_fallo_de_redis_tambien_se_reintenta() -> None:
    assert falla_con_redis.apply(args=(1,)).get() == 2


def test_los_reintentos_tienen_un_limite() -> None:
    resultado = falla_con_la_base.apply(args=(100,))
    assert resultado.failed()
    with pytest.raises(OperationalError):
        resultado.get()
    assert len(llamadas) == 1 + 3


def test_un_error_de_logica_no_se_reintenta() -> None:
    resultado = falla_por_logica.apply()
    assert resultado.failed()
    assert llamadas == ["logica"]


def test_la_sesion_del_job_confirma_y_despues_publica(
    sesion_de_prueba: Session, dos_gerentes: DosGerentes, publicados: Publicados
) -> None:
    gerente = dos_gerentes.uno.gerente
    with sesion_de_trabajo() as db:
        gerente.nombres = "Ana"
        publicar_tras_commit(db, gerente.id, Evento(TipoEvento.NOTIFICACION))
        db.flush()
        assert publicados == []
    sesion_de_prueba.expire_all()
    assert gerente.nombres == "Ana"
    assert len(publicados) == 1


def test_si_el_job_falla_se_deshace_y_no_publica(
    sesion_de_prueba: Session, dos_gerentes: DosGerentes, publicados: Publicados
) -> None:
    gerente = dos_gerentes.uno.gerente
    sesion_de_prueba.commit()
    with pytest.raises(RuntimeError), sesion_de_trabajo() as db:
        gerente.nombres = "Ana"
        publicar_tras_commit(db, gerente.id, Evento(TipoEvento.NOTIFICACION))
        db.flush()
        raise RuntimeError("fallo del job")
    sesion_de_prueba.expire_all()
    assert gerente.nombres is None
    assert publicados == []


def test_el_bloqueo_impide_una_segunda_ejecucion_simultanea(nombre_bloqueo: str) -> None:
    clave = PREFIJO_BLOQUEO + nombre_bloqueo
    with un_solo_a_la_vez(nombre_bloqueo) as primera:
        assert primera is True
        assert 0 < cliente_redis().ttl(clave) <= BLOQUEO_SEGUNDOS
        with un_solo_a_la_vez(nombre_bloqueo) as segunda:
            assert segunda is False
        # La ejecución omitida no libera el bloqueo de la que sigue en curso.
        assert cliente_redis().exists(clave) == 1
    assert cliente_redis().exists(clave) == 0
    with un_solo_a_la_vez(nombre_bloqueo) as despues:
        assert despues is True


def test_el_bloqueo_se_libera_aunque_el_job_falle(nombre_bloqueo: str) -> None:
    with pytest.raises(RuntimeError), un_solo_a_la_vez(nombre_bloqueo):
        raise RuntimeError("fallo del job")
    assert cliente_redis().exists(PREFIJO_BLOQUEO + nombre_bloqueo) == 0


def test_un_bloqueo_vencido_queda_en_el_log(
    nombre_bloqueo: str, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.WARNING, logger="app.workers"):
        with un_solo_a_la_vez(nombre_bloqueo):
            # Simula que el bloqueo expiró mientras el job seguía.
            cliente_redis().delete(PREFIJO_BLOQUEO + nombre_bloqueo)
    assert f"El bloqueo de {nombre_bloqueo} expiró" in caplog.text


def test_sin_redis_el_bloqueo_lanza_un_error_que_se_reintenta(
    nombre_bloqueo: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    caido = redis.Redis.from_url("redis://127.0.0.1:1/0", socket_connect_timeout=1)
    monkeypatch.setattr(base, "cliente_redis", lambda: caido)
    with pytest.raises(redis.ConnectionError), un_solo_a_la_vez(nombre_bloqueo):
        pass
    assert issubclass(redis.ConnectionError, base.ERRORES_TRANSITORIOS)
