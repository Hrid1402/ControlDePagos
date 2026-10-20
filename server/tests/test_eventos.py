import json
import logging
import uuid
from typing import Any

import pytest
import redis
from sqlalchemy.orm import Session

from app.core import eventos
from app.core.eventos import (
    CANAL,
    Evento,
    TipoEvento,
    avisar_cierre_sesion,
    ejecutar_tras_commit,
    publicar,
    publicar_tras_commit,
)
from tests.conftest import DosGerentes

Publicados = list[tuple[uuid.UUID, Evento]]


def test_el_evento_sale_solo_despues_del_commit(
    db: Session, dos_gerentes: DosGerentes, publicados: Publicados
) -> None:
    gerente = dos_gerentes.uno.gerente
    evento = Evento(TipoEvento.NOTIFICACION, {"hola": 1})
    publicar_tras_commit(db, gerente.id, evento)
    db.flush()
    assert publicados == []
    db.commit()
    assert publicados == [(gerente.id, evento)]


def test_el_rollback_descarta_el_evento(
    db: Session, dos_gerentes: DosGerentes, publicados: Publicados
) -> None:
    publicar_tras_commit(db, dos_gerentes.uno.gerente.id, Evento(TipoEvento.NOTIFICACION))
    db.rollback()
    db.commit()
    assert publicados == []


def test_liberar_un_savepoint_no_publica_antes_del_commit(
    db: Session, dos_gerentes: DosGerentes, publicados: Publicados
) -> None:
    with db.begin_nested():
        publicar_tras_commit(db, dos_gerentes.uno.gerente.id, Evento(TipoEvento.NOTIFICACION))
    assert publicados == []
    db.commit()
    assert len(publicados) == 1


def test_deshacer_un_savepoint_descarta_solo_sus_eventos(
    db: Session, dos_gerentes: DosGerentes, publicados: Publicados
) -> None:
    gerente = dos_gerentes.uno.gerente
    antes = Evento(TipoEvento.NOTIFICACION, {"orden": "antes"})
    publicar_tras_commit(db, gerente.id, antes)
    savepoint = db.begin_nested()
    publicar_tras_commit(db, gerente.id, Evento(TipoEvento.NOTIFICACION, {"orden": "dentro"}))
    savepoint.rollback()
    db.commit()
    assert publicados == [(gerente.id, antes)]


def test_cerrar_la_sesion_sin_commit_descarta_los_eventos(
    db: Session, dos_gerentes: DosGerentes, publicados: Publicados
) -> None:
    publicar_tras_commit(db, dos_gerentes.uno.gerente.id, Evento(TipoEvento.NOTIFICACION))
    db.close()
    db.commit()
    assert publicados == []
    assert eventos.PENDIENTES not in db.info


def test_avisar_cierre_de_sesion_encola_el_evento(
    db: Session, dos_gerentes: DosGerentes, publicados: Publicados
) -> None:
    asistente = dos_gerentes.uno.asistente
    avisar_cierre_sesion(db, asistente.id)
    db.commit()
    assert [(u, e.tipo) for u, e in publicados] == [(asistente.id, TipoEvento.SESION_CERRADA)]


def test_el_evento_tiene_id_fecha_de_lima_y_datos() -> None:
    evento = Evento(TipoEvento.NOTIFICACION, {"titulo": "Deuda creada"})
    salida = evento.a_json()
    assert salida["tipo"] == "notificacion"
    assert salida["datos"] == {"titulo": "Deuda creada"}
    assert uuid.UUID(salida["id"]).version == 4
    assert salida["emitido_en"].endswith("-05:00")
    assert Evento(TipoEvento.NOTIFICACION).id != evento.id


def test_publicar_envia_el_evento_por_redis() -> None:
    usuario_id = uuid.uuid4()
    evento = Evento(TipoEvento.NOTIFICACION, {"n": 1})
    suscripcion = eventos.cliente_redis().pubsub()
    suscripcion.subscribe(CANAL)
    try:
        suscripcion.get_message(timeout=2)  # confirmación de la suscripción
        assert publicar(usuario_id, evento) is True
        mensaje = suscripcion.get_message(timeout=2)
    finally:
        suscripcion.close()
    assert mensaje is not None
    assert json.loads(mensaje["data"]) == {"usuario_id": str(usuario_id), "evento": evento.a_json()}


class RedisCaido:
    def publish(self, *_: Any) -> None:
        raise redis.ConnectionError("Redis no responde")


def test_si_redis_falla_el_commit_se_conserva_y_queda_en_el_log(
    db: Session,
    dos_gerentes: DosGerentes,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    gerente = dos_gerentes.uno.gerente
    monkeypatch.setattr(eventos, "cliente_redis", lambda: RedisCaido())
    gerente.nombres = "Ana"
    evento = Evento(TipoEvento.NOTIFICACION)
    publicar_tras_commit(db, gerente.id, evento)
    with caplog.at_level(logging.WARNING, logger="app.tiempo_real"):
        db.commit()
    db.expire_all()
    assert gerente.nombres == "Ana"
    assert str(evento.id) in caplog.text
    assert "No se pudo publicar" in caplog.text


def test_la_accion_se_ejecuta_solo_despues_del_commit_y_en_orden(
    db: Session, dos_gerentes: DosGerentes, publicados: Publicados
) -> None:
    gerente = dos_gerentes.uno.gerente
    orden: list[str] = []
    publicar_tras_commit(db, gerente.id, Evento(TipoEvento.NOTIFICACION))
    ejecutar_tras_commit(db, lambda: orden.append(f"accion tras {len(publicados)} eventos"))
    db.flush()
    assert orden == []
    db.commit()
    assert orden == ["accion tras 1 eventos"]
    assert len(publicados) == 1


def test_el_rollback_descarta_la_accion(db: Session, dos_gerentes: DosGerentes) -> None:
    ejecutadas: list[int] = []
    ejecutar_tras_commit(db, lambda: ejecutadas.append(1))
    db.rollback()
    db.commit()
    assert ejecutadas == []


def test_deshacer_un_savepoint_descarta_solo_sus_acciones(db: Session) -> None:
    ejecutadas: list[str] = []
    ejecutar_tras_commit(db, lambda: ejecutadas.append("antes"))
    savepoint = db.begin_nested()
    ejecutar_tras_commit(db, lambda: ejecutadas.append("dentro"))
    savepoint.rollback()
    db.commit()
    assert ejecutadas == ["antes"]


def test_una_accion_que_falla_no_frena_las_demas_y_queda_en_el_log(
    db: Session,
    dos_gerentes: DosGerentes,
    publicados: Publicados,
    caplog: pytest.LogCaptureFixture,
) -> None:
    def falla() -> None:
        raise RuntimeError("fallo de prueba")

    gerente = dos_gerentes.uno.gerente
    gerente.nombres = "Ana"
    ejecutar_tras_commit(db, falla)
    publicar_tras_commit(db, gerente.id, Evento(TipoEvento.NOTIFICACION))
    with caplog.at_level(logging.ERROR, logger="app.tiempo_real"):
        db.commit()
    db.expire_all()
    assert gerente.nombres == "Ana"
    assert len(publicados) == 1
    assert "Falló una acción posterior al commit" in caplog.text
