"""Catálogo de empresas comunes (H10 CA01 y CA02, TASK-33)."""

import re
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.seguridad import crear_token
from app.main import app
from app.models import Empresa, Usuario
from app.services import empresas
from app.services.empresas import (
    EMPRESAS_COMUNES,
    EmpresaComun,
    clave_catalogo,
    cumple_patron,
    empresa_del_catalogo,
    sincronizar_empresas,
)
from tests.conftest import DosGerentes

IDS = [e.id for e in EMPRESAS_COMUNES]


@pytest.fixture
def cliente(db: Session) -> Iterator[TestClient]:
    # Sin with: no arranca el ciclo de vida, que se suscribe a Redis y estas rutas no usan.
    app.dependency_overrides[get_db] = lambda: db
    yield TestClient(app)
    app.dependency_overrides.clear()


def cabecera(usuario: Usuario) -> dict[str, str]:
    return {"Authorization": f"Bearer {crear_token(usuario)}"}


def comunes_en_tabla(db: Session) -> int:
    return db.scalar(select(func.count()).select_from(Empresa).where(Empresa.id.in_(IDS))) or 0


def test_la_constante_tiene_la_lista_inicial_sin_patrones_ni_repetidos() -> None:
    por_tipo: dict[str, list[str]] = {}
    for empresa in EMPRESAS_COMUNES:
        por_tipo.setdefault(empresa.tipo_servicio, []).append(empresa.nombre)
    assert por_tipo == {
        "luz": ["Hidrandina", "Enel", "Luz del Sur"],
        "agua": ["Sedalib", "Sedapal"],
        "gas": ["Cálidda", "Quavii"],
        "telecomunicaciones": ["Movistar", "Claro", "Entel", "Bitel"],
    }
    assert len(set(IDS)) == len(IDS)
    assert len({clave_catalogo(e.nombre) for e in EMPRESAS_COMUNES}) == len(IDS)


def test_cada_patron_de_la_constante_es_una_expresion_valida() -> None:
    for empresa in EMPRESAS_COMUNES:
        if empresa.patron_codigo is not None:
            re.compile(empresa.patron_codigo)


def test_sincronizar_crea_las_que_faltan_y_repetir_no_duplica(db: Session) -> None:
    sincronizar_empresas(db)
    total = db.scalar(select(func.count()).select_from(Empresa))

    repetida = sincronizar_empresas(db)

    assert comunes_en_tabla(db) == len(EMPRESAS_COMUNES)
    assert db.scalar(select(func.count()).select_from(Empresa)) == total
    assert (repetida.creadas, repetida.actualizadas) == ([], [])
    assert repetida.existentes == [e.nombre for e in EMPRESAS_COMUNES]
    enel = db.get_one(Empresa, EMPRESAS_COMUNES[1].id)
    assert (enel.nombre, enel.tipo_servicio, enel.patron_codigo, enel.ruc) == (
        "Enel",
        "luz",
        None,
        None,
    )


def test_un_patron_nuevo_de_la_constante_se_aplica_y_uno_ausente_no_borra(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    sincronizar_empresas(db)
    primera, segunda, *resto = EMPRESAS_COMUNES
    db.get_one(Empresa, segunda.id).patron_codigo = "[A-Z]{3}"
    db.flush()
    con_patron = EmpresaComun(primera.id, primera.nombre, primera.tipo_servicio, "[0-9]{8}")
    monkeypatch.setattr(empresas, "EMPRESAS_COMUNES", (con_patron, segunda, *resto))

    resultado = sincronizar_empresas(db)

    assert resultado.actualizadas == [primera.nombre]
    assert db.get_one(Empresa, primera.id).patron_codigo == "[0-9]{8}"
    assert db.get_one(Empresa, segunda.id).patron_codigo == "[A-Z]{3}"


def test_el_nombre_manual_coincide_con_el_catalogo_sin_acentos_ni_mayusculas(
    db: Session,
) -> None:
    sincronizar_empresas(db)

    for escrito in ("Calidda", "  CÁLIDDA ", "cálidda"):
        encontrada = empresa_del_catalogo(db, escrito)
        assert encontrada is not None and encontrada.nombre == "Cálidda"
    luz = empresa_del_catalogo(db, "luz   del sur")
    assert luz is not None and luz.nombre == "Luz del Sur"
    assert empresa_del_catalogo(db, "Electro Oriente") is None


def test_sin_patron_cualquier_codigo_vale_y_con_patron_debe_cumplirlo_completo() -> None:
    sin_patron = Empresa(nombre="X", tipo_servicio="otro")
    con_patron = Empresa(nombre="Y", tipo_servicio="otro", patron_codigo="[0-9]{4}")

    assert cumple_patron(sin_patron, "LO-QUE-SEA")
    assert cumple_patron(con_patron, "1234")
    assert not cumple_patron(con_patron, "12345")
    assert not cumple_patron(con_patron, "A1234")


def test_gerente_y_asistente_listan_las_empresas_por_nombre(
    db: Session, cliente: TestClient, dos_gerentes: DosGerentes
) -> None:
    sincronizar_empresas(db)
    equipo = dos_gerentes.uno

    for usuario in (equipo.gerente, equipo.asistente):
        r = cliente.get("/api/v1/empresas", headers=cabecera(usuario))
        assert r.status_code == 200, r.json()
        nombres = [e["nombre"] for e in r.json()]
        assert set(nombres) >= {e.nombre for e in EMPRESAS_COMUNES}
        assert nombres == sorted(nombres)

    sedapal = next(e for e in r.json() if e["nombre"] == "Sedapal")
    assert sedapal == {
        "id": str(EMPRESAS_COMUNES[4].id),
        "nombre": "Sedapal",
        "tipo_servicio": "agua",
        "patron_codigo": None,
    }


def test_filtra_las_empresas_por_tipo_de_servicio(
    db: Session, cliente: TestClient, dos_gerentes: DosGerentes
) -> None:
    sincronizar_empresas(db)

    r = cliente.get(
        "/api/v1/empresas",
        params={"tipo_servicio": "gas"},
        headers=cabecera(dos_gerentes.uno.asistente),
    )

    assert r.status_code == 200
    assert {e["tipo_servicio"] for e in r.json()} == {"gas"}
    assert {"Cálidda", "Quavii"} <= {e["nombre"] for e in r.json()}


def test_empresas_exige_sesion_y_un_tipo_valido(
    cliente: TestClient, dos_gerentes: DosGerentes
) -> None:
    sin_sesion = cliente.get("/api/v1/empresas")
    tipo_invalido = cliente.get(
        "/api/v1/empresas",
        params={"tipo_servicio": "cable"},
        headers=cabecera(dos_gerentes.uno.gerente),
    )

    assert (sin_sesion.status_code, sin_sesion.json()["code"]) == (401, "NO_AUTENTICADO")
    assert (tipo_invalido.status_code, tipo_invalido.json()["field"]) == (422, "tipo_servicio")
