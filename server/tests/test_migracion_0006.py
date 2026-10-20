"""Migración 0006: empresa y código de servicio normalizados en la base (TASK-32).

Usa la misma base temporal que la prueba de la 0005: la compartida está en head toda la sesión.
"""

import uuid

import pytest
from alembic import command
from sqlalchemy import Engine, text
from sqlalchemy.exc import DBAPIError, IntegrityError

from tests.test_migracion_0005 import base_temporal, configuracion, version_de

__all__ = ["base_temporal"]


def preparar_gerente(motor: Engine) -> tuple[uuid.UUID, uuid.UUID]:
    with motor.begin() as conexion:
        gerente = conexion.execute(
            text(
                "INSERT INTO usuario (rol, username, password_hash) "
                "VALUES ('gerente', 'gerente_mig', 'x') RETURNING id"
            )
        ).scalar_one()
        categoria = conexion.execute(
            text(
                "INSERT INTO categoria (gerente_id, nombre, tipo) "
                "VALUES (:g, 'Luz', 'servicio_variable') RETURNING id"
            ),
            {"g": gerente},
        ).scalar_one()
    return gerente, categoria


def insertar(
    motor: Engine, gerente: uuid.UUID, categoria: uuid.UUID, nombre: str, codigo: str
) -> uuid.UUID:
    with motor.begin() as conexion:
        return conexion.execute(
            text(
                "INSERT INTO servicio (gerente_id, categoria_id, empresa_nombre, "
                "codigo_suministro) VALUES (:g, :c, :n, :cod) RETURNING id"
            ),
            {"g": gerente, "c": categoria, "n": nombre, "cod": codigo},
        ).scalar_one()


def leer(motor: Engine, servicio_id: uuid.UUID) -> tuple[str, str]:
    with motor.connect() as conexion:
        fila = conexion.execute(
            text("SELECT empresa_nombre, codigo_suministro FROM servicio WHERE id = :id"),
            {"id": servicio_id},
        ).one()
    return fila[0], fila[1]


def test_normaliza_los_servicios_existentes_y_va_y_vuelve(base_temporal: Engine) -> None:
    config = configuracion()
    command.upgrade(config, "0005")
    gerente, categoria = preparar_gerente(base_temporal)
    servicio = insertar(base_temporal, gerente, categoria, "  Electro   Oriente ", " ab 12 ")

    command.upgrade(config, "0006")

    assert version_de(base_temporal) == "0006"
    assert leer(base_temporal, servicio) == ("Electro Oriente", "AB12")
    with pytest.raises(IntegrityError, match="uq_servicio_codigo"):
        insertar(base_temporal, gerente, categoria, "electro oriente", "ab12")

    command.downgrade(config, "0005")
    assert version_de(base_temporal) == "0005"
    insertar(base_temporal, gerente, categoria, "Electro  Oriente", "AB 13")


def test_se_detiene_si_al_normalizar_quedan_servicios_repetidos(base_temporal: Engine) -> None:
    config = configuracion()
    command.upgrade(config, "0005")
    gerente, categoria = preparar_gerente(base_temporal)
    primero = insertar(base_temporal, gerente, categoria, "Electro Oriente", "AB12")
    insertar(base_temporal, gerente, categoria, "electro  oriente", "ab 12")

    with pytest.raises(DBAPIError, match="1 grupos de servicios quedan con la misma empresa"):
        command.upgrade(config, "0006")

    assert version_de(base_temporal) == "0005"
    assert leer(base_temporal, primero) == ("Electro Oriente", "AB12")


def test_se_detiene_si_hay_un_codigo_en_blanco(base_temporal: Engine) -> None:
    config = configuracion()
    command.upgrade(config, "0005")
    gerente, categoria = preparar_gerente(base_temporal)
    insertar(base_temporal, gerente, categoria, "Electro Oriente", "   ")

    with pytest.raises(DBAPIError, match="1 servicios tienen el código o el nombre"):
        command.upgrade(config, "0006")

    assert version_de(base_temporal) == "0005"
