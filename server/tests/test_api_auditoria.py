"""TASK-18: filtros, paginación, Excel y aislamiento del historial global."""

import uuid
from collections.abc import Iterator
from datetime import datetime
from io import BytesIO

import pytest
from fastapi.testclient import TestClient
from openpyxl import load_workbook
from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.seguridad import crear_token
from app.core.tiempo import zona_horaria
from app.main import app
from app.models import Auditoria, Usuario
from tests.conftest import DosGerentes


@pytest.fixture
def cliente(db: Session) -> Iterator[TestClient]:
    app.dependency_overrides[get_db] = lambda: db
    yield TestClient(app)
    app.dependency_overrides.clear()


def cabecera(usuario: Usuario) -> dict[str, str]:
    return {"Authorization": f"Bearer {crear_token(usuario)}"}


def evento(
    db: Session,
    gerente: Usuario,
    usuario: Usuario,
    accion: str,
    fecha: datetime,
    *,
    nombre: str | None = None,
) -> Auditoria:
    registro = Auditoria(
        gerente_id=gerente.id,
        usuario_id=usuario.id,
        usuario_nombre=nombre or usuario.username,
        accion=accion,
        entidad="usuario",
        entidad_id=usuario.id,
        detalle={"estado": "activa"},
        dispositivo="Navegador",
        creado_en=fecha,
    )
    db.add(registro)
    db.flush()
    return registro


def test_lista_paginada_y_aislada_por_gerente(
    cliente: TestClient, db: Session, dos_gerentes: DosGerentes
) -> None:
    zona = zona_horaria()
    uno, dos = dos_gerentes.uno, dos_gerentes.dos
    reciente = evento(
        db, uno.gerente, uno.asistente, "login_exitoso", datetime(2026, 10, 20, 10, tzinfo=zona)
    )
    anterior = evento(
        db, uno.gerente, uno.gerente, "cuenta_creada", datetime(2026, 10, 19, 10, tzinfo=zona)
    )
    ajeno = evento(
        db, dos.gerente, dos.asistente, "login_exitoso", datetime(2026, 10, 21, 10, tzinfo=zona)
    )

    respuesta = cliente.get(
        "/api/v1/auditoria", params={"page": 1, "size": 1}, headers=cabecera(uno.gerente)
    )
    assert respuesta.status_code == 200
    assert respuesta.json()["total"] == 2
    assert respuesta.json()["page"] == 1
    assert [item["id"] for item in respuesta.json()["items"]] == [str(reciente.id)]
    assert respuesta.json()["items"][0]["detalle"] == {"estado": "activa"}
    assert respuesta.json()["items"][0]["dispositivo"] == "Navegador"
    assert cliente.get(
        "/api/v1/auditoria", params={"page": 2, "size": 1}, headers=cabecera(uno.gerente)
    ).json()["items"][0]["id"] == str(anterior.id)
    assert str(ajeno.id) not in str(respuesta.json())


def test_filtros_por_usuario_accion_y_dia_local(
    cliente: TestClient, db: Session, dos_gerentes: DosGerentes
) -> None:
    zona = zona_horaria()
    equipo = dos_gerentes.uno
    fuera = evento(
        db,
        equipo.gerente,
        equipo.asistente,
        "login_exitoso",
        datetime(2026, 10, 19, 23, 59, tzinfo=zona),
    )
    dentro = evento(
        db,
        equipo.gerente,
        equipo.asistente,
        "login_exitoso",
        datetime(2026, 10, 20, 0, 0, tzinfo=zona),
    )
    evento(
        db, equipo.gerente, equipo.gerente, "login_exitoso", datetime(2026, 10, 20, 12, tzinfo=zona)
    )
    evento(
        db,
        equipo.gerente,
        equipo.asistente,
        "cuenta_activada",
        datetime(2026, 10, 20, 23, 59, tzinfo=zona),
    )
    evento(
        db,
        equipo.gerente,
        equipo.asistente,
        "login_exitoso",
        datetime(2026, 10, 21, 0, 0, tzinfo=zona),
    )
    filtros = {
        "usuario": str(equipo.asistente.id),
        "accion": "login_exitoso",
        "desde": "2026-10-20",
        "hasta": "2026-10-20",
    }
    respuesta = cliente.get("/api/v1/auditoria", params=filtros, headers=cabecera(equipo.gerente))
    assert respuesta.status_code == 200
    assert respuesta.json()["total"] == 1
    assert [item["id"] for item in respuesta.json()["items"]] == [str(dentro.id)]
    assert str(fuera.id) not in str(respuesta.json())


def test_usuario_por_nombre_encuentra_eventos_de_cuenta_eliminada(
    cliente: TestClient, db: Session, dos_gerentes: DosGerentes
) -> None:
    equipo = dos_gerentes.uno
    registro = evento(
        db,
        equipo.gerente,
        equipo.asistente,
        "cuenta_eliminada",
        datetime(2026, 10, 20, tzinfo=zona_horaria()),
        nombre="María Quispe",
    )
    db.execute(delete(Usuario).where(Usuario.id == equipo.asistente.id))
    db.flush()
    db.expire_all()
    respuesta = cliente.get(
        "/api/v1/auditoria", params={"usuario": "quispe"}, headers=cabecera(equipo.gerente)
    )
    assert respuesta.status_code == 200
    assert respuesta.json()["items"][0]["id"] == str(registro.id)
    assert respuesta.json()["items"][0]["usuario_id"] is None


def test_excel_usa_los_mismos_filtros_y_no_ejecuta_formulas(
    cliente: TestClient, db: Session, dos_gerentes: DosGerentes
) -> None:
    equipo = dos_gerentes.uno
    fecha = datetime(2026, 10, 20, 9, 30, tzinfo=zona_horaria())
    evento(db, equipo.gerente, equipo.asistente, "login_exitoso", fecha, nombre="=SUM(1,1)")
    evento(db, equipo.gerente, equipo.asistente, "cuenta_creada", fecha)
    evento(db, dos_gerentes.dos.gerente, dos_gerentes.dos.asistente, "login_exitoso", fecha)

    respuesta = cliente.get(
        "/api/v1/auditoria/exportar",
        params={"accion": "login_exitoso", "desde": "2026-10-20", "hasta": "2026-10-20"},
        headers=cabecera(equipo.gerente),
    )
    assert respuesta.status_code == 200
    assert respuesta.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    assert "attachment" in respuesta.headers["content-disposition"]
    assert respuesta.headers["cache-control"] == "no-store"
    hoja = load_workbook(BytesIO(respuesta.content), read_only=True, data_only=False).active
    assert hoja is not None
    filas = list(hoja.values)
    assert len(filas) == 2
    assert filas[0][:3] == ("Fecha (Lima)", "Usuario", "Acción")
    assert filas[1][0] == fecha.isoformat()
    assert filas[1][1] == "'=SUM(1,1)"
    assert filas[1][2] == "login_exitoso"


def test_autorizacion_y_validacion_en_ambas_rutas(
    cliente: TestClient, db: Session, dos_gerentes: DosGerentes
) -> None:
    equipo = dos_gerentes.uno
    evento(
        db,
        equipo.gerente,
        equipo.gerente,
        "login_exitoso",
        datetime(2026, 10, 20, tzinfo=zona_horaria()),
    )
    for ruta in ("/api/v1/auditoria", "/api/v1/auditoria/exportar"):
        assert cliente.get(ruta).status_code == 401
        prohibida = cliente.get(ruta, headers=cabecera(equipo.asistente))
        assert (prohibida.status_code, prohibida.json()["code"]) == (403, "SIN_PERMISO")
        invalida = cliente.get(
            ruta,
            params={"desde": "2026-10-21", "hasta": "2026-10-20"},
            headers=cabecera(equipo.gerente),
        )
        assert (invalida.status_code, invalida.json()["field"]) == (422, "hasta")
        assert (
            cliente.get(
                ruta, params={"usuario": "  "}, headers=cabecera(equipo.gerente)
            ).status_code
            == 422
        )
    assert cliente.put(
        f"/api/v1/auditoria/{uuid.uuid4()}", headers=cabecera(equipo.gerente)
    ).status_code in (404, 405)
