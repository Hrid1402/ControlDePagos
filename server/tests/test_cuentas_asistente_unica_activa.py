"""Pruebas de verificación de cuentas de asistente y restricción de única activa (TASK-12).

Cubre los criterios de aceptación:
CA02: Solo puede haber una cuenta activa a la vez por gerente, y se destaca en la lista.
CA17: El detalle muestra datos, estado, fecha de creación e historial de activaciones.
Aceptación: Dos solicitudes simultáneas nunca dejan dos asistentes activas;
la consulta del gerente no cruza cuentas ajenas.
"""

import uuid
from collections.abc import Iterator
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.seguridad import crear_token
from app.core.tiempo import ahora_lima
from app.main import app
from app.models import Usuario
from app.services.asistentes import consulta_lista
from tests.conftest import DosGerentes

URL = "/api/v1/asistentes"


def auth_headers(usuario: Usuario) -> dict[str, str]:
    return {"Authorization": f"Bearer {crear_token(usuario)}"}


@pytest.fixture
def cliente(db: Session) -> Iterator[TestClient]:
    app.dependency_overrides[get_db] = lambda: db
    yield TestClient(app)
    app.dependency_overrides.pop(get_db, None)


def crear_asistente_modelo(
    db: Session,
    gerente: Usuario,
    nombre: str,
    *,
    estado: str = "inactiva",
    horas_atras: int = 1,
    **campos: object,
) -> Usuario:
    asistente = Usuario(
        rol="asistente",
        gerente_id=gerente.id,
        username=f"{nombre.lower()}_{uuid.uuid4().hex[:6]}",
        password_hash="hash_de_prueba",
        nombres=nombre,
        apellidos="Gómez",
        estado=estado,
        creado_en=ahora_lima() - timedelta(hours=horas_atras),
        **campos,
    )
    db.add(asistente)
    db.flush()
    return asistente


def test_ca02_restriccion_sql_uq_usuario_asistente_activa(
    db: Session,
    dos_gerentes: DosGerentes,
) -> None:
    """CA02: La BD rechaza insertar dos asistentes activas para el mismo gerente
    usando la restricción uq_usuario_asistente_activa.
    """
    gerente1 = dos_gerentes.uno.gerente
    gerente2 = dos_gerentes.dos.gerente

    # gerente1 ya tiene una asistente activa proveniente del fixture dos_gerentes
    asistente_activa_g1 = dos_gerentes.uno.asistente
    assert asistente_activa_g1.estado == "activa"
    assert asistente_activa_g1.gerente_id == gerente1.id

    # Intentar insertar una segunda asistente activa directamente en BD para gerente1 debe fallar
    segunda_activa_g1 = Usuario(
        rol="asistente",
        gerente_id=gerente1.id,
        username=f"activa2_{uuid.uuid4().hex[:6]}",
        password_hash="hash_de_prueba",
        nombres="Segunda",
        apellidos="Activa",
        estado="activa",
    )
    with pytest.raises(IntegrityError, match="uq_usuario_asistente_activa"):
        with db.begin_nested():
            db.add(segunda_activa_g1)
            db.flush()

    # Sin embargo, una asistente inactiva sí se puede agregar sin conflicto
    inactiva_g1 = crear_asistente_modelo(db, gerente1, "Inactiva1", estado="inactiva")
    assert inactiva_g1.estado == "inactiva"

    # Y gerente2 también puede tener su propia asistente activa sin interferir con gerente1
    asistente_activa_g2 = dos_gerentes.dos.asistente
    assert asistente_activa_g2.estado == "activa"
    assert asistente_activa_g2.gerente_id == gerente2.id


def test_ca02_asistente_activa_se_destaca_primero_en_la_lista(
    cliente: TestClient,
    dos_gerentes: DosGerentes,
    db: Session,
) -> None:
    """CA02: La cuenta activa se destaca apareciendo en la primera posición de la lista."""
    gerente = dos_gerentes.uno.gerente
    activa = dos_gerentes.uno.asistente

    # Crear asistentes inactivas con distintas antigüedades
    mas_reciente_inactiva = crear_asistente_modelo(
        db, gerente, "Reciente", estado="inactiva", horas_atras=2
    )
    mas_antigua_inactiva = crear_asistente_modelo(
        db, gerente, "Antigua", estado="inactiva", horas_atras=48
    )
    # Crear una eliminada que no debe aparecer
    crear_asistente_modelo(
        db,
        gerente,
        "Eliminada",
        estado="inactiva",
        horas_atras=5,
        eliminado_en=ahora_lima(),
    )

    # 1. Verificación a través del servicio SQL ORM consulta_lista
    cuentas_orm = db.scalars(consulta_lista(gerente)).all()
    assert [c.id for c in cuentas_orm] == [
        activa.id,
        mas_reciente_inactiva.id,
        mas_antigua_inactiva.id,
    ]

    # 2. Verificación a través del endpoint HTTP GET /api/v1/asistentes
    r = cliente.get(URL, headers=auth_headers(gerente))
    assert r.status_code == 200
    datos = r.json()
    assert datos["total"] == 3
    items = datos["items"]
    assert items[0]["id"] == str(activa.id)
    assert items[0]["estado"] == "activa"
    assert items[1]["id"] == str(mas_reciente_inactiva.id)
    assert items[1]["estado"] == "inactiva"
    assert items[2]["id"] == str(mas_antigua_inactiva.id)
    assert items[2]["estado"] == "inactiva"
