"""Los bloqueos del ciclo de cuenta (TASK-14) no frenan las llaves foráneas hacia esas filas.

Con FOR UPDATE, una auditoría que referencia al gerente o a la asistente esperaba al bloqueo, y si
esa transacción ya tenía bloqueada a la asistente, PostgreSQL cortaba una de las dos por
interbloqueo (test_cuenta_concurrencia.py lo mostraba de forma intermitente). Aquí se comprueba de
forma determinista: la segunda transacción no espera, o fallaría por lock_timeout.
"""

import uuid
from collections.abc import Callable, Iterator

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.models import Auditoria, Usuario
from app.services.asistentes import bloquear_asistente_propia, bloquear_gerente


@pytest.fixture
def equipo() -> Iterator[tuple[uuid.UUID, uuid.UUID]]:
    marca = uuid.uuid4().hex[:10]
    with SessionLocal() as db:
        gerente = Usuario(rol="gerente", username=f"g_bloqueo_{marca}", password_hash="x")
        db.add(gerente)
        db.flush()
        asistente = Usuario(
            rol="asistente", gerente_id=gerente.id, username=f"a_bloqueo_{marca}", password_hash="x"
        )
        db.add(asistente)
        db.commit()
        ids = (gerente.id, asistente.id)
    yield ids
    with SessionLocal() as db:
        parametros = {"g": ids[0]}
        db.execute(text("DELETE FROM usuario WHERE gerente_id = :g"), parametros)
        db.execute(text("DELETE FROM usuario WHERE id = :g"), parametros)
        db.commit()


def insertar_auditoria_sin_esperar(gerente_id: uuid.UUID, usuario_id: uuid.UUID) -> None:
    """Inserta una auditoría con llaves foráneas al gerente y al usuario y la deshace."""
    with SessionLocal() as db:
        db.execute(text("SET LOCAL lock_timeout = '1s'"))
        db.add(
            Auditoria(
                gerente_id=gerente_id,
                usuario_id=usuario_id,
                usuario_nombre="Prueba",
                accion="contrasena_restablecida",
                entidad="usuario",
                entidad_id=usuario_id,
            )
        )
        db.flush()
        db.rollback()


@pytest.mark.parametrize(
    "bloquear",
    [
        pytest.param(lambda db, g, _a: bloquear_gerente(db, g), id="gerente"),
        pytest.param(lambda db, g, a: bloquear_asistente_propia(db, g, a), id="asistente"),
    ],
)
def test_el_bloqueo_no_frena_una_auditoria_que_referencia_la_fila(
    equipo: tuple[uuid.UUID, uuid.UUID],
    bloquear: Callable[[Session, Usuario, uuid.UUID], object],
) -> None:
    gerente_id, asistente_id = equipo
    with SessionLocal() as db:
        bloquear(db, db.get_one(Usuario, gerente_id), asistente_id)
        # Mientras el bloqueo sigue tomado, otra transacción referencia ambas filas.
        insertar_auditoria_sin_esperar(gerente_id, asistente_id)
        db.rollback()
