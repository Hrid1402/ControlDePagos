"""Comentarios de una deuda (H17 CA06, TASK-54)."""

import uuid
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.eventos import Evento
from app.main import app
from app.models import Notificacion
from tests.conftest import DosGerentes, nueva_deuda
from tests.test_api_comprobantes import cabecera


@pytest.fixture
def cliente(db: Session) -> Iterator[TestClient]:
    app.dependency_overrides[get_db] = lambda: db
    yield TestClient(app)
    app.dependency_overrides.clear()


def ruta(deuda_id: uuid.UUID) -> str:
    return f"/api/v1/deudas/{deuda_id}/comentarios"


def test_conversan_y_cada_comentario_avisa_al_otro_rol(
    cliente: TestClient,
    db: Session,
    dos_gerentes: DosGerentes,
    publicados: list[tuple[uuid.UUID, Evento]],
) -> None:
    equipo = dos_gerentes.uno
    deuda = nueva_deuda(db, equipo.gerente)

    r = cliente.post(
        ruta(deuda.id), headers=cabecera(equipo.asistente), json={"texto": " Ya pagué "}
    )
    assert r.status_code == 201, r.json()
    assert (r.json()["texto"], r.json()["rol"], r.json()["propio"]) == (
        "Ya pagué",
        "asistente",
        True,
    )
    cliente.post(ruta(deuda.id), headers=cabecera(equipo.gerente), json={"texto": "Gracias"})

    lista = cliente.get(ruta(deuda.id), headers=cabecera(equipo.gerente)).json()
    assert [(c["texto"], c["propio"]) for c in lista] == [("Ya pagué", False), ("Gracias", True)]
    avisos = list(db.scalars(select(Notificacion).where(Notificacion.tipo == "comentario")))
    assert {a.usuario_id for a in avisos} == {equipo.gerente.id, equipo.asistente.id}
    assert any(a.mensaje.endswith(": Ya pagué") for a in avisos)


@pytest.mark.parametrize("texto", ["", "   ", "x" * 501])
def test_el_texto_va_de_1_a_500_caracteres(
    cliente: TestClient, db: Session, dos_gerentes: DosGerentes, texto: str
) -> None:
    deuda = nueva_deuda(db, dos_gerentes.uno.gerente)

    r = cliente.post(
        ruta(deuda.id), headers=cabecera(dos_gerentes.uno.gerente), json={"texto": texto}
    )

    assert (r.status_code, r.json()["field"]) == (422, "texto")


def test_anulada_no_admite_comentarios_y_otro_gerente_no_los_ve(
    cliente: TestClient, db: Session, dos_gerentes: DosGerentes
) -> None:
    anulada = nueva_deuda(db, dos_gerentes.uno.gerente, estado="anulada")
    r = cliente.post(
        ruta(anulada.id), headers=cabecera(dos_gerentes.uno.gerente), json={"texto": "x"}
    )
    assert (r.status_code, r.json()["code"]) == (409, "ESTADO_NO_PERMITIDO")

    for metodo in ("get", "post"):
        r = cliente.request(
            metodo,
            ruta(anulada.id),
            headers=cabecera(dos_gerentes.dos.asistente),
            json={"texto": "x"},
        )
        assert (r.status_code, r.json()["code"]) == (404, "NO_ENCONTRADO")
