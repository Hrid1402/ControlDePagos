import uuid
from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencias import SesionDb
from app.core.errores import registrar_manejadores
from app.core.paginacion import Pagina, Paginacion, ParametrosPagina, paginar
from app.models import Categoria, Usuario
from tests.conftest import DosGerentes

prueba = FastAPI()
registrar_manejadores(prueba)


class CategoriaSalida(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    nombre: str


@prueba.get("/gerentes/{gerente_id}/categorias", response_model=Pagina[CategoriaSalida])
def listar(gerente_id: uuid.UUID, db: SesionDb, pagina: ParametrosPagina) -> Pagina[Categoria]:
    # Todas comparten tipo: sin desempate por id, el orden entre páginas no sería estable.
    consulta = select(Categoria).where(Categoria.gerente_id == gerente_id).order_by(Categoria.tipo)
    return paginar(db, consulta, pagina)


@pytest.fixture
def cliente(db: Session) -> Iterator[TestClient]:
    prueba.dependency_overrides[get_db] = lambda: db
    yield TestClient(prueba)
    prueba.dependency_overrides.clear()


def crear_categorias(db: Session, gerente: Usuario, cantidad: int) -> list[Categoria]:
    categorias = [
        Categoria(gerente_id=gerente.id, nombre=f"Categoría {n:02d}", tipo="servicio_variable")
        for n in range(cantidad)
    ]
    db.add_all(categorias)
    db.flush()
    return categorias


def test_total_sobre_el_filtro_completo_con_varias_paginas(
    cliente: TestClient, db: Session, dos_gerentes: DosGerentes
) -> None:
    gerente = dos_gerentes.uno.gerente
    crear_categorias(db, gerente, 25)
    crear_categorias(db, dos_gerentes.dos.gerente, 3)
    url = f"/gerentes/{gerente.id}/categorias"

    primera = cliente.get(url, params={"size": 10}).json()
    ultima = cliente.get(url, params={"page": 3, "size": 10}).json()
    vacia = cliente.get(url, params={"page": 4, "size": 10}).json()

    assert (primera["total"], primera["page"], len(primera["items"])) == (25, 1, 10)
    assert (ultima["total"], ultima["page"], len(ultima["items"])) == (25, 3, 5)
    assert (vacia["total"], vacia["items"]) == (25, [])


def test_recorrer_las_paginas_no_repite_ni_pierde_elementos(
    cliente: TestClient, db: Session, dos_gerentes: DosGerentes
) -> None:
    gerente = dos_gerentes.uno.gerente
    esperadas = {str(c.id) for c in crear_categorias(db, gerente, 23)}
    vistas: list[str] = []
    for page in range(1, 6):
        r = cliente.get(f"/gerentes/{gerente.id}/categorias", params={"page": page, "size": 5})
        vistas += [item["id"] for item in r.json()["items"]]
    assert len(vistas) == len(set(vistas)) == 23
    assert set(vistas) == esperadas


def test_tamano_por_defecto_es_20(
    cliente: TestClient, db: Session, dos_gerentes: DosGerentes
) -> None:
    gerente = dos_gerentes.uno.gerente
    crear_categorias(db, gerente, 21)
    cuerpo = cliente.get(f"/gerentes/{gerente.id}/categorias").json()
    assert (cuerpo["page"], cuerpo["total"], len(cuerpo["items"])) == (1, 21, 20)


@pytest.mark.parametrize(
    ("params", "campo"),
    [({"size": 101}, "size"), ({"size": 0}, "size"), ({"page": 0}, "page")],
)
def test_parametros_fuera_de_rango_responden_422_con_el_campo(
    cliente: TestClient, params: dict[str, int], campo: str
) -> None:
    r = cliente.get(f"/gerentes/{uuid.uuid4()}/categorias", params=params)
    assert r.status_code == 422
    assert r.json() == {"detail": "El valor no es válido.", "code": "VALIDACION", "field": campo}


def test_sin_order_by_ordena_por_id(db: Session, dos_gerentes: DosGerentes) -> None:
    gerente = dos_gerentes.uno.gerente
    categorias = crear_categorias(db, gerente, 6)
    consulta = select(Categoria).where(Categoria.gerente_id == gerente.id)

    pagina = paginar(db, consulta, Paginacion(page=2, size=4))

    ids = sorted(c.id for c in categorias)
    assert [c.id for c in pagina.items] == ids[4:]
    assert (pagina.total, pagina.page) == (6, 2)
