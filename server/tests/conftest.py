import os
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy.orm import Session

os.environ["DATABASE_URL"] = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+psycopg://postgres:postgres@localhost:5432/control_pagos_test",
)
# Las pruebas no dependen de la clave del .env de cada desarrollador.
os.environ.setdefault("JWT_SECRET", "clave-de-pruebas-clave-de-pruebas")

from app.models import Usuario  # noqa: E402


@dataclass
class Equipo:
    gerente: Usuario
    asistente: Usuario


@dataclass
class DosGerentes:
    uno: Equipo
    dos: Equipo


@pytest.fixture(scope="session", autouse=True)
def esquema() -> None:
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    command.upgrade(config, "head")


@pytest.fixture
def db() -> Iterator[Session]:
    from app.core.database import engine

    with engine.connect() as conexion:
        transaccion = conexion.begin()
        sesion = Session(bind=conexion, join_transaction_mode="create_savepoint")
        yield sesion
        sesion.close()
        transaccion.rollback()


def crear_equipo(db: Session, sufijo: str) -> Equipo:
    gerente = Usuario(rol="gerente", username=f"gerente_{sufijo}", password_hash="x")
    db.add(gerente)
    db.flush()
    asistente = Usuario(
        rol="asistente", gerente_id=gerente.id, username=f"asistente_{sufijo}", password_hash="x"
    )
    db.add(asistente)
    db.flush()
    db.refresh(gerente)
    db.refresh(asistente)
    return Equipo(gerente=gerente, asistente=asistente)


@pytest.fixture
def dos_gerentes(db: Session) -> DosGerentes:
    """Dos gerentes, cada uno con su asistente activa, para probar el aislamiento."""
    return DosGerentes(uno=crear_equipo(db, "uno"), dos=crear_equipo(db, "dos"))
