"""Lista y detalle de asistentes del gerente (TASK-11, H03 CA01, CA02 y CA17)."""

import uuid
from collections.abc import Iterator
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.seguridad import crear_token
from app.core.tiempo import ahora_lima
from app.main import app
from app.models import Usuario
from tests.conftest import DosGerentes

URL = "/api/v1/asistentes"


def auth(usuario: Usuario) -> dict[str, str]:
    return {"Authorization": f"Bearer {crear_token(usuario)}"}


@pytest.fixture
def cliente(db: Session) -> Iterator[TestClient]:
    app.dependency_overrides[get_db] = lambda: db
    yield TestClient(app)
    app.dependency_overrides.pop(get_db, None)


def cuenta(
    db: Session, gerente: Usuario, nombre: str, horas_atras: int, **campos: object
) -> Usuario:
    nueva = Usuario(
        rol="asistente",
        gerente_id=gerente.id,
        username=f"{nombre.lower()}_{uuid.uuid4().hex[:6]}",
        password_hash="x",
        nombres=nombre,
        apellidos="Prueba",
        estado="inactiva",
        creado_en=ahora_lima() - timedelta(hours=horas_atras),
        **campos,
    )
    db.add(nueva)
    db.flush()
    return nueva


def test_la_lista_pone_primero_la_activa_y_luego_las_mas_recientes(
    cliente: TestClient, dos_gerentes: DosGerentes, db: Session
) -> None:
    gerente = dos_gerentes.uno.gerente
    activa = dos_gerentes.uno.asistente
    antigua = cuenta(db, gerente, "Antigua", horas_atras=48)
    reciente = cuenta(db, gerente, "Reciente", horas_atras=1, ultimo_ingreso=ahora_lima())
    cuenta(db, gerente, "Eliminada", horas_atras=2, eliminado_en=ahora_lima())

    r = cliente.get(URL, headers=auth(gerente))

    assert r.status_code == 200
    datos = r.json()
    assert [fila["id"] for fila in datos["items"]] == [
        str(activa.id),
        str(reciente.id),
        str(antigua.id),
    ]
    assert datos["total"] == 3
    fila = datos["items"][1]
    assert set(fila) >= {
        "nombres",
        "apellidos",
        "username",
        "estado",
        "ultimo_ingreso",
        "creado_en",
    }
    assert fila["ultimo_ingreso"] is not None
    assert datos["items"][2]["ultimo_ingreso"] is None


def test_la_lista_es_paginada_y_solo_del_gerente(
    cliente: TestClient, dos_gerentes: DosGerentes, db: Session
) -> None:
    gerente = dos_gerentes.uno.gerente
    for n in range(3):
        cuenta(db, gerente, f"Extra{n}", horas_atras=n + 1)

    r = cliente.get(URL, params={"page": 2, "size": 2}, headers=auth(gerente))

    assert r.json()["total"] == 4
    assert r.json()["page"] == 2
    assert len(r.json()["items"]) == 2
    ajenas = {str(dos_gerentes.dos.asistente.id)}
    todas = cliente.get(URL, params={"size": 100}, headers=auth(gerente)).json()["items"]
    assert ajenas.isdisjoint({fila["id"] for fila in todas})


def test_la_asistente_no_ve_la_lista(cliente: TestClient, dos_gerentes: DosGerentes) -> None:
    r = cliente.get(URL, headers=auth(dos_gerentes.uno.asistente))
    assert r.status_code == 403


def test_el_detalle_trae_el_historial_con_quien_hizo_cada_cambio(
    cliente: TestClient, dos_gerentes: DosGerentes, db: Session
) -> None:
    gerente = dos_gerentes.uno.gerente
    gerente.nombres, gerente.apellidos = "Carla", "Vega"
    nueva = cuenta(db, gerente, "Nueva", horas_atras=3)
    cliente.post(f"{URL}/{nueva.id}/activar", headers=auth(gerente))
    cliente.post(f"{URL}/{nueva.id}/desactivar", headers=auth(gerente))

    r = cliente.get(f"{URL}/{nueva.id}", headers=auth(gerente))

    assert r.status_code == 200
    detalle = r.json()
    assert detalle["id"] == str(nueva.id)
    assert detalle["estado"] == "inactiva"
    assert detalle["creado_en"] is not None
    assert [e["accion"] for e in detalle["historial"]] == ["desactivada", "activada"]
    assert {e["realizada_por"] for e in detalle["historial"]} == {"Carla Vega"}


def test_una_cuenta_sin_cambios_tiene_historial_vacio(
    cliente: TestClient, dos_gerentes: DosGerentes, db: Session
) -> None:
    gerente = dos_gerentes.uno.gerente
    nueva = cuenta(db, gerente, "Quieta", horas_atras=1)
    r = cliente.get(f"{URL}/{nueva.id}", headers=auth(gerente))
    assert r.json()["historial"] == []


def test_el_detalle_ajeno_o_eliminado_no_revela_datos(
    cliente: TestClient, dos_gerentes: DosGerentes, db: Session
) -> None:
    gerente = dos_gerentes.uno.gerente
    eliminada = cuenta(db, gerente, "Baja", horas_atras=1, eliminado_en=ahora_lima())
    for asistente_id in (dos_gerentes.dos.asistente.id, eliminada.id, uuid.uuid4()):
        r = cliente.get(f"{URL}/{asistente_id}", headers=auth(gerente))
        assert r.status_code == 404
        assert r.json()["code"] == "NO_ENCONTRADO"
    # La ruta de disponibilidad sigue respondiendo aunque comparta el prefijo.
    disponible = cliente.get(
        f"{URL}/disponibilidad", params={"username": "libre.ok"}, headers=auth(gerente)
    )
    assert disponible.status_code == 200
