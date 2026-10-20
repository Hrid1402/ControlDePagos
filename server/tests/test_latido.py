import json
import logging
import uuid
from collections.abc import Iterator
from dataclasses import dataclass

import pytest
from celery.contrib.testing.worker import start_worker

from app.core.eventos import cliente_redis
from app.workers import latido as modulo_latido
from app.workers.base import PREFIJO_BLOQUEO, un_solo_a_la_vez
from app.workers.celery_app import celery_app
from app.workers.latido import VIGENCIA_SEGUNDOS, latido


@dataclass
class LatidoAislado:
    clave: str
    bloqueo: str


@pytest.fixture
def aislado(monkeypatch: pytest.MonkeyPatch) -> Iterator[LatidoAislado]:
    """Clave y bloqueo propios de la prueba, para no tocar el latido de un worker local. Al
    terminar se borran de Redis."""
    marca = uuid.uuid4().hex
    datos = LatidoAislado(clave=f"pruebas:latido:{marca}", bloqueo=f"pruebas-latido-{marca}")
    monkeypatch.setattr(modulo_latido, "CLAVE_LATIDO", datos.clave)
    monkeypatch.setattr(modulo_latido, "BLOQUEO_LATIDO", datos.bloqueo)
    try:
        yield datos
    finally:
        cliente_redis().delete(datos.clave, PREFIJO_BLOQUEO + datos.bloqueo)


def leer(clave: str) -> dict[str, str]:
    valor = cliente_redis().get(clave)
    assert valor is not None
    datos: dict[str, str] = json.loads(valor)
    return datos


def test_el_latido_guarda_la_hora_de_lima_y_la_de_la_base(aislado: LatidoAislado) -> None:
    registro = latido.apply().get()

    assert registro == leer(aislado.clave)
    assert registro["ejecutado_en"].endswith("-05:00")
    assert registro["hora_base"].endswith("-05:00")
    assert 0 < cliente_redis().ttl(aislado.clave) <= VIGENCIA_SEGUNDOS


def test_repetir_el_latido_solo_reemplaza_el_registro(aislado: LatidoAislado) -> None:
    primero = latido.apply().get()
    segundo = latido.apply().get()

    assert leer(aislado.clave) == segundo
    assert segundo["ejecutado_en"] >= primero["ejecutado_en"]
    assert cliente_redis().keys(f"{aislado.clave}*") == [aislado.clave.encode()]


def test_con_otra_ejecucion_en_curso_el_latido_no_hace_nada(aislado: LatidoAislado) -> None:
    with un_solo_a_la_vez(aislado.bloqueo) as tomado:
        assert tomado
        assert latido.apply().get() is None
    assert cliente_redis().get(aislado.clave) is None
    assert cliente_redis().exists(PREFIJO_BLOQUEO + aislado.bloqueo) == 0


@pytest.fixture
def registro_raiz() -> Iterator[None]:
    """El worker de prueba reconfigura el logging de la raíz; se restaura al terminar para no
    afectar a las demás pruebas."""
    raiz = logging.getLogger()
    nivel, manejadores = raiz.level, list(raiz.handlers)
    try:
        yield
    finally:
        raiz.setLevel(nivel)
        raiz.handlers[:] = manejadores


def test_un_worker_real_ejecuta_el_latido_desde_su_cola(
    aislado: LatidoAislado, registro_raiz: None
) -> None:
    cola = f"pruebas-{uuid.uuid4().hex}"
    redis = cliente_redis()
    resultado = None
    try:
        with start_worker(
            celery_app,
            pool="solo",
            loglevel="WARNING",
            perform_ping_check=False,
            queues=[cola],
            shutdown_timeout=10,
        ):
            resultado = latido.apply_async(queue=cola, ignore_result=False)
            registro = resultado.get(timeout=10)
        assert registro == leer(aislado.clave)
        assert registro["ejecutado_en"].endswith("-05:00")
    finally:
        if resultado is not None:
            resultado.forget()
        redis.delete(cola, f"_kombu.binding.{cola}")
    assert redis.keys(f"*{cola}*") == []
    assert redis.exists(f"celery-task-meta-{resultado.id}") == 0
