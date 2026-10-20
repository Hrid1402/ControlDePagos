import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.seguridad import crear_token
from app.main import app
from app.models import Deuda, OrdenPago, Servicio, Usuario
from tests.conftest import DosGerentes, Equipo, nueva_deuda, nueva_orden

PENDIENTES = "/api/v1/ordenes/pendientes"
AHORA = datetime.now(UTC)


@pytest.fixture
def cliente(db: Session) -> Iterator[TestClient]:
    # Sin with: no arranca el ciclo de vida, que se suscribe a Redis y estas rutas no usan.
    app.dependency_overrides[get_db] = lambda: db
    yield TestClient(app)
    app.dependency_overrides.clear()


def cabecera(usuario: Usuario) -> dict[str, str]:
    return {"Authorization": f"Bearer {crear_token(usuario)}"}


def ruta(orden: OrdenPago, accion: str) -> str:
    return f"/api/v1/ordenes/{orden.id}/{accion}"


def orden_de(db: Session, equipo: Equipo, estado: str = "enviada", **opciones: Any) -> OrdenPago:
    deuda = nueva_deuda(db, equipo.gerente)
    return nueva_orden(db, deuda, estado=estado, asistente=equipo.asistente, **opciones)


def ids(respuesta: Any) -> list[str]:
    return [item["id"] for item in respuesta.json()["items"]]


def test_pendientes_trae_solo_las_suyas_sin_responder_y_la_mas_urgente_primero(
    cliente: TestClient, db: Session, dos_gerentes: DosGerentes
) -> None:
    equipo = dos_gerentes.uno
    sin_plazo = orden_de(db, equipo)
    tarde = orden_de(db, equipo, "vista", plazo=AHORA + timedelta(hours=3))
    pronto = orden_de(db, equipo, plazo=AHORA + timedelta(hours=1))
    for estado in ("aceptada", "rechazada", "cancelada", "pagada"):
        orden_de(db, equipo, estado)
    orden_de(db, dos_gerentes.dos)

    r = cliente.get(PENDIENTES, headers=cabecera(equipo.asistente))

    assert r.status_code == 200
    assert ids(r) == [str(pronto.id), str(tarde.id), str(sin_plazo.id)]
    assert (r.json()["total"], r.json()["page"]) == (3, 1)
    item = r.json()["items"][0]
    assert (item["estado"], item["version"], item["monto"], item["moneda"]) == (
        "enviada",
        "enviada:0",
        "100.00",
        "PEN",
    )
    servicio = db.get_one(Servicio, db.get_one(Deuda, pronto.deuda_id).servicio_id)
    assert (item["empresa"], item["codigo_suministro"]) == (
        "Hidrandina",
        servicio.codigo_suministro,
    )


def test_pendientes_pagina_con_orden_estable(
    cliente: TestClient, db: Session, dos_gerentes: DosGerentes
) -> None:
    equipo = dos_gerentes.uno
    ordenes = [orden_de(db, equipo) for _ in range(3)]
    # Mismo plazo y misma creación: el id decide.
    for orden in ordenes:
        orden.creado_en = AHORA
    db.flush()

    paginas = [
        cliente.get(PENDIENTES, params={"page": n, "size": 2}, headers=cabecera(equipo.asistente))
        for n in (1, 2)
    ]

    assert ids(paginas[0]) + ids(paginas[1]) == sorted(str(o.id) for o in ordenes)
    assert [p.json()["total"] for p in paginas] == [3, 3]


def test_pendientes_es_solo_de_la_asistente(
    cliente: TestClient, db: Session, dos_gerentes: DosGerentes
) -> None:
    r = cliente.get(PENDIENTES, headers=cabecera(dos_gerentes.uno.gerente))

    assert r.status_code == 403
    assert r.json() == {
        "detail": "No tienes permiso para realizar esta acción.",
        "code": "SIN_PERMISO",
        "field": None,
    }


@pytest.mark.parametrize("caso", ["sin_token", "revocado", "inactiva"])
def test_sesion_no_valida_recibe_401(
    cliente: TestClient, db: Session, dos_gerentes: DosGerentes, caso: str
) -> None:
    equipo = dos_gerentes.uno
    orden = orden_de(db, equipo)
    cabeceras = cabecera(equipo.asistente)
    if caso == "sin_token":
        cabeceras = {}
    if caso == "revocado":
        equipo.asistente.token_version += 1
    if caso == "inactiva":
        equipo.asistente.estado = "inactiva"
    db.flush()
    codigo = {
        "sin_token": "NO_AUTENTICADO",
        "revocado": "SESION_REVOCADA",
        "inactiva": "CUENTA_INACTIVA",
    }[caso]

    for respuesta in (
        cliente.get(PENDIENTES, headers=cabeceras),
        cliente.post(ruta(orden, "vista"), headers=cabeceras),
        cliente.post(ruta(orden, "aceptar"), headers=cabeceras),
        cliente.post(ruta(orden, "rechazar"), json={"motivo": "otro_medio"}, headers=cabeceras),
    ):
        assert (respuesta.status_code, respuesta.json()["code"]) == (401, codigo)
    assert orden.estado == "enviada"


def test_vista_y_su_repeticion(cliente: TestClient, db: Session, dos_gerentes: DosGerentes) -> None:
    equipo = dos_gerentes.uno
    orden = orden_de(db, equipo)

    primera = cliente.post(ruta(orden, "vista"), headers=cabecera(equipo.asistente))
    segunda = cliente.post(ruta(orden, "vista"), headers=cabecera(equipo.asistente))

    assert primera.status_code == segunda.status_code == 200
    assert (primera.json()["repetido"], segunda.json()["repetido"]) == (False, True)
    assert primera.json()["orden"]["estado"] == "vista"
    assert primera.json()["orden"]["vista_en"] == segunda.json()["orden"]["vista_en"]


def test_aceptar_responde_la_deuda_en_proceso(
    cliente: TestClient, db: Session, dos_gerentes: DosGerentes
) -> None:
    equipo = dos_gerentes.uno
    orden = orden_de(db, equipo)

    r = cliente.post(ruta(orden, "aceptar"), headers=cabecera(equipo.asistente))

    assert r.status_code == 200
    cuerpo = r.json()
    assert (cuerpo["resultado"], cuerpo["repetido"]) == ("iniciado", False)
    assert (cuerpo["orden"]["estado"], cuerpo["orden"]["version"]) == ("aceptada", "aceptada:0")
    assert cuerpo["deuda"]["estado"] == "en_proceso"
    assert cuerpo["deuda"]["pago_iniciado_por"] == str(equipo.asistente.id)
    assert cuerpo["deuda"]["saldo"] == "100.00"

    repetido = cliente.post(ruta(orden, "aceptar"), headers=cabecera(equipo.asistente))
    assert (repetido.status_code, repetido.json()["repetido"]) == (200, True)


def test_aceptar_con_el_importe_cambiado_responde_409_y_no_cambia_nada(
    cliente: TestClient, db: Session, dos_gerentes: DosGerentes
) -> None:
    equipo = dos_gerentes.uno
    orden = orden_de(db, equipo)
    deuda = db.get_one(Deuda, orden.deuda_id)
    deuda.monto = Decimal("150.00")
    db.flush()

    r = cliente.post(ruta(orden, "aceptar"), headers=cabecera(equipo.asistente))

    assert r.status_code == 409
    assert r.json() == {
        "detail": "La orden ya no autoriza este pago. Revisa la deuda de nuevo.",
        "code": "ORDEN_NO_VALIDA",
        "field": None,
    }
    db.expire_all()
    assert (orden.estado, orden.aceptada_en) == ("enviada", None)
    assert (deuda.estado, deuda.pago_iniciado_por) == ("pendiente", None)
    pendientes = cliente.get(PENDIENTES, headers=cabecera(equipo.asistente))
    assert ids(pendientes) == [str(orden.id)]


def test_rechazar_responde_el_motivo(
    cliente: TestClient, db: Session, dos_gerentes: DosGerentes
) -> None:
    equipo = dos_gerentes.uno
    orden = orden_de(db, equipo)

    r = cliente.post(
        ruta(orden, "rechazar"),
        json={"motivo": "agente_cerrado", "detalle": "Cerró a las 6"},
        headers=cabecera(equipo.asistente),
    )

    assert r.status_code == 200
    salida = r.json()["orden"]
    assert (salida["estado"], salida["motivo"], salida["detalle"]) == (
        "rechazada",
        "agente_cerrado",
        "Cerró a las 6",
    )
    assert db.get_one(Deuda, orden.deuda_id).estado == "pendiente"
    assert cliente.get(PENDIENTES, headers=cabecera(equipo.asistente)).json()["items"] == []


@pytest.mark.parametrize(
    ("cuerpo", "campo"),
    [
        ({}, "motivo"),
        ({"motivo": "no_existe"}, "motivo"),
        ({"motivo": "otro"}, "detalle"),
        ({"motivo": "otro", "detalle": "x" * 301}, "detalle"),
    ],
)
def test_rechazar_con_datos_invalidos_responde_422(
    cliente: TestClient,
    db: Session,
    dos_gerentes: DosGerentes,
    cuerpo: dict[str, str],
    campo: str,
) -> None:
    equipo = dos_gerentes.uno
    orden = orden_de(db, equipo)

    r = cliente.post(ruta(orden, "rechazar"), json=cuerpo, headers=cabecera(equipo.asistente))

    assert r.status_code == 422
    assert (r.json()["code"], r.json()["field"]) == ("VALIDACION", campo)
    assert orden.estado == "enviada"


def test_dos_gerentes_no_ven_ni_responden_ordenes_ajenas(
    cliente: TestClient, db: Session, dos_gerentes: DosGerentes
) -> None:
    ajena = orden_de(db, dos_gerentes.dos)
    intrusa = cabecera(dos_gerentes.uno.asistente)

    assert cliente.get(PENDIENTES, headers=intrusa).json()["items"] == []
    for accion, cuerpo in (
        ("vista", None),
        ("aceptar", None),
        ("rechazar", {"motivo": "otro_medio"}),
    ):
        r = cliente.post(ruta(ajena, accion), json=cuerpo, headers=intrusa)
        assert (r.status_code, r.json()["code"]) == (404, "NO_ENCONTRADO")
    assert ajena.estado == "enviada"
    inexistente = cliente.post(f"/api/v1/ordenes/{uuid.uuid4()}/vista", headers=intrusa)
    assert inexistente.status_code == 404


def test_cancelada_responde_409_para_cerrar_con_aviso(
    cliente: TestClient, db: Session, dos_gerentes: DosGerentes
) -> None:
    equipo = dos_gerentes.uno
    orden = orden_de(db, equipo, "cancelada")

    for accion, cuerpo in (
        ("vista", None),
        ("aceptar", None),
        ("rechazar", {"motivo": "otro_medio"}),
    ):
        r = cliente.post(ruta(orden, accion), json=cuerpo, headers=cabecera(equipo.asistente))
        assert r.json() == {
            "detail": "El gerente canceló esta orden.",
            "code": "ORDEN_CANCELADA",
            "field": None,
        }
