import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy.orm import Session

os.environ["DATABASE_URL"] = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+psycopg://postgres:postgres@localhost:5432/control_pagos_test",
)


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
