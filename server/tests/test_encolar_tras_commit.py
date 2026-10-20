import json
import logging
import uuid
from collections.abc import Iterator
from typing import Any

import pytest
from celery import Celery
from celery.canvas import Signature
from sqlalchemy.orm import Session

from app.core import eventos
from app.core.eventos import Evento, TipoEvento, publicar_tras_commit
from app.workers import encolar as modulo_encolar
from app.workers.celery_app import celery_app
from app.workers.encolar import encolar, encolar_tras_commit
from tests.conftest import DosGerentes

TAREA = "pruebas.encolar_tras_commit"


@pytest.fixture
def enviadas(monkeypatch: pytest.MonkeyPatch) -> list[Signature]:
    """Captura las tareas que se encolan tras el commit en lugar de enviarlas a Redis."""
    salida: list[Signature] = []

    def capturar(firma: Signature) -> bool:
        salida.append(firma)
        return True

    monkeypatch.setattr(modulo_encolar, "encolar", capturar)
    return salida


@pytest.fixture
def cola_unica() -> Iterator[str]:
    """Cola propia de la prueba, que ningún worker local consume. Al terminar se borran la cola y
    su registro en Redis."""
    cola = f"pruebas-{uuid.uuid4().hex}"
    try:
        yield cola
    finally:
        eventos.cliente_redis().delete(cola, f"_kombu.binding.{cola}")


def test_la_tarea_se_encola_solo_despues_del_commit(
    db: Session, dos_gerentes: DosGerentes, enviadas: list[Signature]
) -> None:
    firma = celery_app.signature(TAREA, args=(str(dos_gerentes.uno.gerente.id),))
    encolar_tras_commit(db, firma)
    db.flush()
    assert enviadas == []
    db.commit()
    assert enviadas == [firma]


def test_el_rollback_no_encola_la_tarea(
    db: Session, dos_gerentes: DosGerentes, enviadas: list[Signature]
) -> None:
    encolar_tras_commit(db, celery_app.signature(TAREA))
    db.rollback()
    db.commit()
    assert enviadas == []


def test_deshacer_un_savepoint_descarta_solo_sus_tareas(
    db: Session, dos_gerentes: DosGerentes, enviadas: list[Signature]
) -> None:
    antes = celery_app.signature(TAREA, args=("antes",))
    encolar_tras_commit(db, antes)
    savepoint = db.begin_nested()
    encolar_tras_commit(db, celery_app.signature(TAREA, args=("dentro",)))
    savepoint.rollback()
    db.commit()
    assert enviadas == [antes]


def test_eventos_y_tareas_salen_en_el_orden_en_que_se_encolaron(
    db: Session,
    dos_gerentes: DosGerentes,
    enviadas: list[Signature],
    publicados: list[tuple[uuid.UUID, Evento]],
) -> None:
    orden: list[str] = []
    gerente = dos_gerentes.uno.gerente
    publicar_tras_commit(db, gerente.id, Evento(TipoEvento.NOTIFICACION))
    encolar_tras_commit(db, celery_app.signature(TAREA))
    eventos.ejecutar_tras_commit(db, lambda: orden.append(f"{len(publicados)}-{len(enviadas)}"))
    db.commit()
    assert orden == ["1-1"]


def test_si_el_broker_no_responde_el_commit_se_conserva_y_queda_en_el_log(
    db: Session, dos_gerentes: DosGerentes, caplog: pytest.LogCaptureFixture
) -> None:
    caido = Celery("pruebas", broker="redis://127.0.0.1:1/0")
    caido.conf.update(
        task_publish_retry_policy=celery_app.conf.task_publish_retry_policy,
        broker_transport_options=celery_app.conf.broker_transport_options,
    )
    resultados: list[bool] = []
    firma = caido.signature(TAREA, args=("dato-que-no-debe-registrarse",))
    gerente = dos_gerentes.uno.gerente
    gerente.nombres = "Ana"
    eventos.ejecutar_tras_commit(db, lambda: resultados.append(encolar(firma)))
    with caplog.at_level(logging.WARNING, logger="app.workers"):
        db.commit()
    db.expire_all()
    assert gerente.nombres == "Ana"
    assert resultados == [False]
    assert f"No se pudo encolar la tarea {TAREA}" in caplog.text
    assert "dato-que-no-debe-registrarse" not in caplog.text


def test_tras_el_commit_el_mensaje_llega_a_la_cola_de_redis(
    db: Session, dos_gerentes: DosGerentes, cola_unica: str
) -> None:
    gerente_id = str(dos_gerentes.uno.gerente.id)
    encolar_tras_commit(db, celery_app.signature(TAREA, args=(gerente_id,)).set(queue=cola_unica))
    redis = eventos.cliente_redis()
    assert redis.llen(cola_unica) == 0
    db.commit()
    mensajes = redis.lrange(cola_unica, 0, -1)
    assert len(mensajes) == 1
    mensaje: dict[str, Any] = json.loads(mensajes[0])
    assert mensaje["headers"]["task"] == TAREA
    assert mensaje["content-type"] == "application/json"
