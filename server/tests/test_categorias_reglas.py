"""Reglas de categorías que la pantalla explica (H09, TASK-29).

CA01: las precargadas no se eliminan. CA03: el tipo define los campos de la deuda, así que no
cambia ni se mueven sus servicios a otro tipo mientras haya deudas o recurrencias. CA06: la lista
cuenta servicios y deudas.
"""

from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.seguridad import crear_token
from app.main import app
from app.models import Categoria, Recurrencia, Servicio, Usuario
from tests.conftest import DosGerentes, nueva_categoria, nueva_deuda

URL = "/api/v1/categorias"


@pytest.fixture
def cliente(db: Session) -> Iterator[TestClient]:
    app.dependency_overrides[get_db] = lambda: db
    yield TestClient(app)
    app.dependency_overrides.clear()


def cabecera(usuario: Usuario) -> dict[str, str]:
    return {"Authorization": f"Bearer {crear_token(usuario)}"}


def servicio_en(db: Session, categoria: Categoria) -> Servicio:
    servicio = Servicio(
        gerente_id=categoria.gerente_id,
        categoria_id=categoria.id,
        empresa_nombre="Empresa",
        codigo_suministro=f"COD-{categoria.id.hex[:8]}",
    )
    db.add(servicio)
    db.flush()
    return servicio


def fila(cliente: TestClient, gerente: Usuario, categoria: Categoria) -> dict[str, Any]:
    filas = cliente.get(URL, headers=cabecera(gerente)).json()
    encontrada: dict[str, Any] = next(f for f in filas if f["id"] == str(categoria.id))
    return encontrada


def test_ca01_una_precargada_no_se_elimina(
    cliente: TestClient, db: Session, dos_gerentes: DosGerentes
) -> None:
    gerente = dos_gerentes.uno.gerente
    luz = Categoria(gerente_id=gerente.id, nombre="Luz", tipo="servicio_variable", precargada=True)
    db.add(luz)
    db.flush()

    r = cliente.delete(f"{URL}/{luz.id}", headers=cabecera(gerente))

    assert (r.status_code, r.json()["code"]) == (409, "CATEGORIA_PRECARGADA")
    assert db.get(Categoria, luz.id) is not None


def test_ca06_la_lista_cuenta_servicios_y_deudas_vigentes(
    cliente: TestClient, db: Session, dos_gerentes: DosGerentes
) -> None:
    gerente = dos_gerentes.uno.gerente
    categoria = nueva_categoria(db, gerente)
    nueva_deuda(db, gerente, categoria=categoria)
    nueva_deuda(db, gerente, categoria=categoria)
    nueva_deuda(db, gerente, categoria=categoria, estado="anulada")
    vacia = nueva_categoria(db, gerente)

    contada = fila(cliente, gerente, categoria)
    assert (contada["cantidad_servicios"], contada["cantidad_deudas"]) == (3, 2)
    assert fila(cliente, gerente, vacia)["cantidad_deudas"] == 0
    detalle = cliente.get(f"{URL}/{categoria.id}", headers=cabecera(gerente)).json()
    assert detalle["cantidad_deudas"] == 2


def test_ca03_no_se_mueven_servicios_con_deudas_a_otro_tipo(
    cliente: TestClient, db: Session, dos_gerentes: DosGerentes
) -> None:
    gerente = dos_gerentes.uno.gerente
    origen = nueva_categoria(db, gerente, "servicio_variable")
    nueva_deuda(db, gerente, categoria=origen)
    tarjeta = nueva_categoria(db, gerente, "tarjeta")
    mismo_tipo = nueva_categoria(db, gerente, "servicio_variable")

    otro = cliente.post(
        f"{URL}/{origen.id}/mover-servicios",
        json={"destino_id": str(tarjeta.id)},
        headers=cabecera(gerente),
    )
    al_eliminar = cliente.delete(
        f"{URL}/{origen.id}", params={"mover_a": str(tarjeta.id)}, headers=cabecera(gerente)
    )
    mismo = cliente.post(
        f"{URL}/{origen.id}/mover-servicios",
        json={"destino_id": str(mismo_tipo.id)},
        headers=cabecera(gerente),
    )

    assert (otro.status_code, otro.json()["code"], otro.json()["field"]) == (
        409,
        "TIPO_INCOMPATIBLE",
        "destino_id",
    )
    assert (al_eliminar.status_code, al_eliminar.json()["field"]) == (409, "mover_a")
    assert db.get(Categoria, origen.id) is not None
    assert mismo.status_code == 200
    assert mismo.json()["servicios_movidos"] == 1


def test_ca03_una_recurrencia_tambien_ata_el_tipo(
    cliente: TestClient, db: Session, dos_gerentes: DosGerentes
) -> None:
    gerente = dos_gerentes.uno.gerente
    origen = nueva_categoria(db, gerente, "monto_fijo")
    servicio = servicio_en(db, origen)
    db.add(Recurrencia(servicio_id=servicio.id, tipo="variable", dia_vencimiento=15))
    db.flush()
    prestamo = nueva_categoria(db, gerente, "prestamo")

    r = cliente.post(
        f"{URL}/{origen.id}/mover-servicios",
        json={"destino_id": str(prestamo.id)},
        headers=cabecera(gerente),
    )
    assert (r.status_code, r.json()["code"]) == (409, "TIPO_INCOMPATIBLE")


def test_ca03_servicios_sin_deudas_ni_recurrencias_se_mueven_a_otro_tipo(
    cliente: TestClient, db: Session, dos_gerentes: DosGerentes
) -> None:
    gerente = dos_gerentes.uno.gerente
    origen = nueva_categoria(db, gerente, "servicio_variable")
    servicio_en(db, origen)
    tarjeta = nueva_categoria(db, gerente, "tarjeta")

    r = cliente.delete(
        f"{URL}/{origen.id}", params={"mover_a": str(tarjeta.id)}, headers=cabecera(gerente)
    )
    assert (r.status_code, r.json()["servicios_movidos"]) == (200, 1)


def test_ca03_el_tipo_no_cambia_mientras_tenga_deudas(
    cliente: TestClient, db: Session, dos_gerentes: DosGerentes
) -> None:
    gerente = dos_gerentes.uno.gerente
    usada = nueva_categoria(db, gerente, "servicio_variable")
    nueva_deuda(db, gerente, categoria=usada)
    libre = nueva_categoria(db, gerente, "servicio_variable")

    bloqueada = cliente.put(
        f"{URL}/{usada.id}",
        json={"nombre": usada.nombre, "tipo": "tarjeta", "color": "#123456"},
        headers=cabecera(gerente),
    )
    mismo_tipo = cliente.put(
        f"{URL}/{usada.id}",
        json={"nombre": "Renombrada", "tipo": "servicio_variable"},
        headers=cabecera(gerente),
    )
    cambiada = cliente.put(
        f"{URL}/{libre.id}",
        json={"nombre": libre.nombre, "tipo": "tarjeta"},
        headers=cabecera(gerente),
    )

    assert (bloqueada.status_code, bloqueada.json()["code"], bloqueada.json()["field"]) == (
        409,
        "TIPO_EN_USO",
        "tipo",
    )
    db.refresh(usada)
    assert (usada.tipo, usada.color) == ("servicio_variable", "#64748B")
    assert mismo_tipo.json()["nombre"] == "Renombrada"
    assert cambiada.json()["tipo"] == "tarjeta"
