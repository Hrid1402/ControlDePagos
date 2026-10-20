"""Migración 0005: monto NULL en deuda solo para esperando_recibo y anulada.

Se prueba en una base temporal propia, creada y borrada en cada corrida: la base compartida de
las pruebas está migrada a head por toda la sesión y no se puede bajar sin afectar a las demás.
"""

import uuid
from collections.abc import Iterator
from datetime import date
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError, IntegrityError, OperationalError, ProgrammingError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import Categoria, Deuda, Servicio, Usuario

PRIVILEGIO_INSUFICIENTE = "42501"


def configuracion() -> Config:
    return Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))


@pytest.fixture
def base_temporal(monkeypatch: pytest.MonkeyPatch) -> Iterator[Engine]:
    """Base vacía con nombre único. Se omite la prueba si el usuario no puede crear bases."""
    origen = make_url(settings.database_url)
    nombre = f"control_pagos_mig_{uuid.uuid4().hex[:12]}"
    administracion = create_engine(origen, isolation_level="AUTOCOMMIT")
    try:
        with administracion.connect() as conexion:
            conexion.execute(text(f'CREATE DATABASE "{nombre}"'))
    except (ProgrammingError, OperationalError) as error:
        administracion.dispose()
        if getattr(error.orig, "sqlstate", None) == PRIVILEGIO_INSUFICIENTE:
            pytest.skip(f"El usuario de la base no puede crear bases de datos: {error.orig}")
        raise
    destino = origen.set(database=nombre)
    monkeypatch.setattr(settings, "database_url", destino.render_as_string(hide_password=False))
    motor = create_engine(destino)
    try:
        yield motor
    finally:
        motor.dispose()
        with administracion.connect() as conexion:
            conexion.execute(text(f'DROP DATABASE IF EXISTS "{nombre}" WITH (FORCE)'))
        administracion.dispose()


def monto_admite_nulo(motor: Engine) -> bool:
    with motor.connect() as conexion:
        return (
            conexion.execute(
                text(
                    "SELECT is_nullable FROM information_schema.columns "
                    "WHERE table_name = 'deuda' AND column_name = 'monto'"
                )
            ).scalar_one()
            == "YES"
        )


def version_de(motor: Engine) -> str:
    with motor.connect() as conexion:
        return conexion.execute(text("SELECT version_num FROM alembic_version")).scalar_one()


def insertar_deuda_sin_monto(motor: Engine, estado: str = "esperando_recibo") -> uuid.UUID:
    with Session(motor) as sesion:
        gerente = Usuario(rol="gerente", username="gerente_mig", password_hash="x")
        sesion.add(gerente)
        sesion.flush()
        categoria = Categoria(gerente_id=gerente.id, nombre="Luz", tipo="servicio_variable")
        sesion.add(categoria)
        sesion.flush()
        servicio = Servicio(
            gerente_id=gerente.id,
            categoria_id=categoria.id,
            empresa_nombre="Hidrandina",
            codigo_suministro="123456",
        )
        sesion.add(servicio)
        sesion.flush()
        deuda = Deuda(
            gerente_id=gerente.id,
            servicio_id=servicio.id,
            periodo=date(2026, 10, 1),
            monto=None,
            estado=estado,
            fecha_vencimiento=date(2026, 10, 20),
        )
        sesion.add(deuda)
        sesion.commit()
        return deuda.id


def test_ida_y_vuelta_de_la_migracion(base_temporal: Engine) -> None:
    config = configuracion()
    command.upgrade(config, "0005")
    assert version_de(base_temporal) == "0005"
    assert monto_admite_nulo(base_temporal)

    command.downgrade(config, "0004")
    assert version_de(base_temporal) == "0004"
    assert not monto_admite_nulo(base_temporal)
    with pytest.raises(IntegrityError, match="monto"):
        insertar_deuda_sin_monto(base_temporal)

    command.upgrade(config, "0005")
    assert monto_admite_nulo(base_temporal)
    insertar_deuda_sin_monto(base_temporal)


def test_el_downgrade_con_deudas_sin_monto_falla_sin_tocar_datos(base_temporal: Engine) -> None:
    config = configuracion()
    command.upgrade(config, "0005")
    deuda_id = insertar_deuda_sin_monto(base_temporal)

    with pytest.raises(DBAPIError, match="No se puede deshacer la migración 0005"):
        command.downgrade(config, "0004")

    assert version_de(base_temporal) == "0005"
    assert monto_admite_nulo(base_temporal)
    with Session(base_temporal) as sesion:
        deuda = sesion.get_one(Deuda, deuda_id)
        assert deuda.monto is None
        assert deuda.estado == "esperando_recibo"


def test_el_downgrade_funciona_si_las_deudas_sin_monto_se_resuelven(
    base_temporal: Engine,
) -> None:
    config = configuracion()
    command.upgrade(config, "0005")
    deuda_id = insertar_deuda_sin_monto(base_temporal, estado="anulada")
    with pytest.raises(DBAPIError, match="No se puede deshacer"):
        command.downgrade(config, "0004")

    with base_temporal.begin() as conexion:
        conexion.execute(text("DELETE FROM deuda WHERE id = :id"), {"id": deuda_id})
    command.downgrade(config, "0004")
    assert version_de(base_temporal) == "0004"
