import uuid
from collections.abc import Iterator
from datetime import datetime, time, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.seguridad import crear_token
from app.core.tiempo import ahora_lima, zona_horaria
from app.main import app
from app.models import Auditoria, Servicio, Usuario
from tests.conftest import DosGerentes, en_proceso_por, nueva_categoria, nueva_deuda, nueva_orden

HOY = ahora_lima().date()


@pytest.fixture
def cliente(db: Session) -> Iterator[TestClient]:
    # Sin with: no arranca el ciclo de vida, que se suscribe a Redis y estas rutas no usan.
    app.dependency_overrides[get_db] = lambda: db
    yield TestClient(app)
    app.dependency_overrides.clear()


def cabecera(usuario: Usuario) -> dict[str, str]:
    return {"Authorization": f"Bearer {crear_token(usuario)}"}


def ver(cliente: TestClient, usuario: Usuario, **parametros: Any) -> dict[str, Any]:
    r = cliente.get("/api/v1/bandeja", params=parametros, headers=cabecera(usuario))
    assert r.status_code == 200, r.json()
    cuerpo: dict[str, Any] = r.json()
    return cuerpo


def fijar_ruta(deuda_id: uuid.UUID) -> str:
    return f"/api/v1/deudas/{deuda_id}/fijar"


def recordar_ruta(deuda_id: uuid.UUID) -> str:
    return f"/api/v1/deudas/{deuda_id}/recordar-manana"


def ids(cuerpo: dict[str, Any]) -> list[str]:
    return [item["id"] for item in cuerpo["items"]]


def acciones(db: Session, deuda_id: uuid.UUID, accion: str) -> list[Auditoria]:
    return list(
        db.scalars(
            select(Auditoria)
            .where(Auditoria.entidad_id == deuda_id, Auditoria.accion == accion)
            .order_by(Auditoria.creado_en, Auditoria.id)
        )
    )


def test_todo_al_dia_responde_una_lista_vacia(
    cliente: TestClient, dos_gerentes: DosGerentes
) -> None:
    cuerpo = ver(cliente, dos_gerentes.uno.asistente)

    assert cuerpo == {
        "items": [],
        "total": 0,
        "page": 1,
        "contadores": {"por_pagar": 0, "por_validar": 0, "rechazadas": 0},
    }


def test_cada_deuda_trae_sus_datos_y_su_prioridad(
    cliente: TestClient, db: Session, dos_gerentes: DosGerentes
) -> None:
    equipo = dos_gerentes.uno
    deuda = nueva_deuda(db, equipo.gerente, monto="85.40", fecha_vencimiento=HOY)
    servicio = db.get(Servicio, deuda.servicio_id)
    assert servicio is not None
    servicio.alias = "Casa"
    servicio.lugar_pago = "agente_bcp"
    db.flush()

    (item,) = ver(cliente, equipo.asistente)["items"]

    assert item["id"] == str(deuda.id)
    assert (item["empresa"], item["alias"], item["lugar_pago"]) == (
        "Hidrandina",
        "Casa",
        "agente_bcp",
    )
    assert (item["monto"], item["saldo"], item["moneda"]) == ("85.40", "85.40", "PEN")
    assert (item["nivel"], item["etiqueta"], item["dias_restantes"]) == (3, "vence_hoy", 0)
    assert item["categoria"]["tipo"] == "servicio_variable"
    assert (item["fijada"], item["orden_urgente"], item["en_proceso"]) == (False, None, None)


def test_en_proceso_indica_si_paga_el_gerente_o_la_asistente(
    cliente: TestClient, db: Session, dos_gerentes: DosGerentes
) -> None:
    equipo = dos_gerentes.uno
    equipo.gerente.nombres, equipo.gerente.apellidos = "Ana", "Ríos"
    de_gerente = nueva_deuda(db, equipo.gerente, fecha_vencimiento=HOY)
    de_asistente = nueva_deuda(db, equipo.gerente, fecha_vencimiento=HOY + timedelta(days=1))
    # El gerente ya no inicia pagos (TASK-109); un intento suyo anterior se sigue mostrando.
    en_proceso_por(db, de_gerente, equipo.gerente)
    r = cliente.post(
        f"/api/v1/deudas/{de_asistente.id}/iniciar-pago", headers=cabecera(equipo.asistente)
    )
    assert r.json()["resultado"] == "iniciado"

    items = ver(cliente, equipo.asistente)["items"]

    assert [(i["estado"], i["en_proceso"]["rol"], i["en_proceso"]["nombre"]) for i in items] == [
        ("en_proceso", "gerente", "Ana Ríos"),
        ("en_proceso", "asistente", equipo.asistente.username),
    ]
    assert items[1]["en_proceso"]["usuario_id"] == str(equipo.asistente.id)
    assert items[1]["en_proceso"]["desde"] is not None


def test_dos_gerentes_no_ven_ni_tocan_deudas_ajenas(
    cliente: TestClient, db: Session, dos_gerentes: DosGerentes
) -> None:
    uno, dos = dos_gerentes.uno, dos_gerentes.dos
    deuda = nueva_deuda(db, uno.gerente)
    categoria = nueva_categoria(db, uno.gerente)

    assert ids(ver(cliente, uno.gerente)) == ids(ver(cliente, uno.asistente)) == [str(deuda.id)]
    assert ver(cliente, dos.asistente)["contadores"]["por_pagar"] == 0
    for r in (
        cliente.post(fijar_ruta(deuda.id), json={"fijada": True}, headers=cabecera(dos.asistente)),
        cliente.post(recordar_ruta(deuda.id), headers=cabecera(dos.asistente)),
    ):
        assert (r.status_code, r.json()["code"]) == (404, "NO_ENCONTRADO")
    r = cliente.get(
        "/api/v1/bandeja", params={"categoria": str(categoria.id)}, headers=cabecera(dos.gerente)
    )
    assert r.status_code == 404
    assert (r.json()["code"], r.json()["field"]) == ("NO_ENCONTRADO", "categoria")
    db.refresh(deuda)
    assert (deuda.fijada, deuda.oculta_hasta) == (False, None)


def test_permisos_y_validacion(cliente: TestClient, db: Session, dos_gerentes: DosGerentes) -> None:
    equipo = dos_gerentes.uno
    deuda = nueva_deuda(db, equipo.gerente)

    r = cliente.get("/api/v1/bandeja")
    assert (r.status_code, r.json()["code"]) == (401, "NO_AUTENTICADO")
    for r in (
        cliente.post(fijar_ruta(deuda.id), json={"fijada": True}, headers=cabecera(equipo.gerente)),
        cliente.post(recordar_ruta(deuda.id), headers=cabecera(equipo.gerente)),
    ):
        assert (r.status_code, r.json()["code"]) == (403, "SIN_PERMISO")
    r = cliente.get(
        "/api/v1/bandeja", params={"pestana": "todas"}, headers=cabecera(equipo.asistente)
    )
    assert (r.status_code, r.json()["code"], r.json()["field"]) == (422, "VALIDACION", "pestana")
    r = cliente.post(
        fijar_ruta(deuda.id), json={"fijada": "si"}, headers=cabecera(equipo.asistente)
    )
    assert (r.status_code, r.json()["code"], r.json()["field"]) == (422, "VALIDACION", "fijada")


def test_fijar_y_desfijar_audita_solo_los_cambios(
    cliente: TestClient, db: Session, dos_gerentes: DosGerentes
) -> None:
    equipo = dos_gerentes.uno
    fijada = nueva_deuda(db, equipo.gerente, fecha_vencimiento=HOY + timedelta(days=20))
    otra = nueva_deuda(db, equipo.gerente, fecha_vencimiento=HOY + timedelta(days=2))

    for valor in (True, True):
        r = cliente.post(
            fijar_ruta(fijada.id), json={"fijada": valor}, headers=cabecera(equipo.asistente)
        )
        assert r.status_code == 200
        assert r.json() == {"id": str(fijada.id), "fijada": True, "oculta_hasta": None}
    items = ver(cliente, equipo.asistente)["items"]
    assert [(i["id"], i["etiqueta"]) for i in items] == [
        (str(fijada.id), "fijada"),
        (str(otra.id), "proxima"),
    ]

    r = cliente.post(
        fijar_ruta(fijada.id), json={"fijada": False}, headers=cabecera(equipo.asistente)
    )
    assert r.json()["fijada"] is False
    assert ids(ver(cliente, equipo.asistente)) == [str(otra.id), str(fijada.id)]
    eventos = acciones(db, fijada.id, "deuda_fijada")
    assert [e.detalle for e in eventos] == [{"fijada": True}, {"fijada": False}]
    assert {e.usuario_id for e in eventos} == {equipo.asistente.id}


def test_fijar_en_proceso_sin_comprobante_si_y_por_validar_no(
    cliente: TestClient, db: Session, dos_gerentes: DosGerentes
) -> None:
    equipo = dos_gerentes.uno
    en_proceso = nueva_deuda(db, equipo.gerente)
    cliente.post(f"/api/v1/deudas/{en_proceso.id}/iniciar-pago", headers=cabecera(equipo.gerente))

    r = cliente.post(
        fijar_ruta(en_proceso.id), json={"fijada": True}, headers=cabecera(equipo.asistente)
    )
    assert (r.status_code, r.json()["fijada"]) == (200, True)

    for estado in ("por_validar", "pagada", "anulada"):
        deuda = nueva_deuda(db, equipo.gerente, estado=estado)
        r = cliente.post(
            fijar_ruta(deuda.id), json={"fijada": True}, headers=cabecera(equipo.asistente)
        )
        assert (r.status_code, r.json()["code"]) == (409, "ESTADO_NO_PERMITIDO"), estado
        db.refresh(deuda)
        assert deuda.fijada is False


def test_recordar_manana_saca_la_deuda_y_baja_el_contador(
    cliente: TestClient, db: Session, dos_gerentes: DosGerentes
) -> None:
    equipo = dos_gerentes.uno
    pospuesta = nueva_deuda(db, equipo.gerente)
    queda = nueva_deuda(db, equipo.gerente)
    assert ver(cliente, equipo.asistente)["total"] == 2

    r = cliente.post(recordar_ruta(pospuesta.id), headers=cabecera(equipo.asistente))

    assert r.status_code == 200
    manana = datetime.combine(ahora_lima().date() + timedelta(days=1), time(8), zona_horaria())
    assert datetime.fromisoformat(r.json()["oculta_hasta"]) == manana
    cuerpo = ver(cliente, equipo.asistente)
    assert (ids(cuerpo), cuerpo["total"], cuerpo["contadores"]["por_pagar"]) == (
        [str(queda.id)],
        1,
        1,
    )
    assert len(acciones(db, pospuesta.id, "deuda_pospuesta")) == 1


def test_recordar_manana_con_orden_urgente_responde_409(
    cliente: TestClient, db: Session, dos_gerentes: DosGerentes
) -> None:
    equipo = dos_gerentes.uno
    deuda = nueva_deuda(db, equipo.gerente)
    nueva_orden(db, deuda, asistente=equipo.asistente)

    r = cliente.post(recordar_ruta(deuda.id), headers=cabecera(equipo.asistente))

    assert (r.status_code, r.json()["code"]) == (409, "ORDEN_URGENTE_ACTIVA")
    (item,) = ver(cliente, equipo.asistente)["items"]
    assert item["etiqueta"] == "orden_urgente"
    assert item["orden_urgente"]["estado"] == "enviada"


def test_paginas_de_uno_sin_repetidos_ni_omitidos(
    cliente: TestClient, db: Session, dos_gerentes: DosGerentes
) -> None:
    equipo = dos_gerentes.uno
    deudas = [nueva_deuda(db, equipo.gerente, fecha_vencimiento=HOY) for _ in range(3)]
    nueva_deuda(db, equipo.gerente, estado="por_validar")

    paginas = [ver(cliente, equipo.asistente, size=1, page=n) for n in (1, 2, 3, 4)]

    vistos = [i for p in paginas[:3] for i in ids(p)]
    assert vistos == sorted(str(d.id) for d in deudas)
    assert paginas[3]["items"] == []
    assert {p["total"] for p in paginas} == {3}
    assert all(
        p["contadores"] == {"por_pagar": 3, "por_validar": 1, "rechazadas": 0} for p in paginas
    )
    assert [p["page"] for p in paginas] == [1, 2, 3, 4]


def test_la_deuda_esperando_recibo_sin_monto_no_aparece_ni_cuenta(
    cliente: TestClient, db: Session, dos_gerentes: DosGerentes
) -> None:
    equipo = dos_gerentes.uno
    pendiente = nueva_deuda(db, equipo.gerente)
    nueva_deuda(db, equipo.gerente, monto=None, estado="esperando_recibo")

    cuerpo = ver(cliente, equipo.asistente)

    assert ids(cuerpo) == [str(pendiente.id)]
    assert cuerpo["total"] == 1
