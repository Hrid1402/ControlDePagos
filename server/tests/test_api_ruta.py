"""Ruta de pagos presenciales (H23, TASK-79): agrupación, inicio en lote y pago declarado."""

import uuid
from collections.abc import Iterator
from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.seguridad import crear_token
from app.main import app
from app.models import Auditoria, Deuda, Limite, Servicio, Usuario
from tests.conftest import DosGerentes, nueva_deuda, nuevo_comprobante


@pytest.fixture
def cliente(db: Session) -> Iterator[TestClient]:
    app.dependency_overrides[get_db] = lambda: db
    yield TestClient(app)
    app.dependency_overrides.clear()


def cabecera(usuario: Usuario) -> dict[str, str]:
    return {"Authorization": f"Bearer {crear_token(usuario)}"}


def con_lugar(db: Session, deuda: Deuda, lugar: str | None) -> Deuda:
    servicio = db.get(Servicio, deuda.servicio_id)
    assert servicio is not None
    servicio.lugar_pago = lugar
    db.flush()
    return deuda


def en_proceso_de(db: Session, deuda: Deuda, usuario: Usuario) -> Deuda:
    deuda.estado = "en_proceso"
    deuda.pago_iniciado_por = usuario.id
    deuda.pago_iniciado_en = func.now()
    db.flush()
    db.refresh(deuda)
    return deuda


def declaraciones(db: Session, deuda: Deuda) -> int:
    return (
        db.scalar(
            select(func.count())
            .select_from(Auditoria)
            .where(Auditoria.entidad_id == deuda.id, Auditoria.accion == "pago_declarado")
        )
        or 0
    )


def test_agrupa_por_lugar_sin_banca_movil_ni_lo_que_paga_otro(
    cliente: TestClient, db: Session, dos_gerentes: DosGerentes
) -> None:
    equipo = dos_gerentes.uno
    bcp_1 = con_lugar(
        db,
        nueva_deuda(db, equipo.gerente, "85.40", fecha_vencimiento=date(2026, 10, 28)),
        "agente_bcp",
    )
    bcp_2 = con_lugar(
        db,
        nueva_deuda(db, equipo.gerente, "20.00", "USD", fecha_vencimiento=date(2026, 10, 22)),
        "agente_bcp",
    )
    kasnet = con_lugar(db, nueva_deuda(db, equipo.gerente, "62.10"), "agente_kasnet")
    sin_lugar = nueva_deuda(db, equipo.gerente, "10.00")
    con_lugar(db, nueva_deuda(db, equipo.gerente, "40.00"), "banca_movil")
    mia = en_proceso_de(
        db,
        con_lugar(db, nueva_deuda(db, equipo.gerente, "30.00"), "agente_kasnet"),
        equipo.asistente,
    )
    en_proceso_de(
        db, con_lugar(db, nueva_deuda(db, equipo.gerente, "50.00"), "agente_bcp"), equipo.gerente
    )
    con_lugar(db, nueva_deuda(db, equipo.gerente, None, estado="esperando_recibo"), "agente_bcp")
    con_lugar(db, nueva_deuda(db, equipo.gerente, "70.00", estado="pagada"), "agente_bcp")
    con_lugar(db, nueva_deuda(db, dos_gerentes.dos.gerente, "99.00"), "agente_bcp")

    r = cliente.get("/api/v1/ruta", headers=cabecera(equipo.asistente))

    assert r.status_code == 200
    cuerpo = r.json()
    assert [g["lugar"] for g in cuerpo["grupos"]] == ["agente_bcp", "agente_kasnet", None]
    bcp, agente_kasnet, ninguno = cuerpo["grupos"]
    # Por vencimiento dentro del grupo; los totales por moneda, sin sumar soles con dólares.
    assert [i["id"] for i in bcp["items"]] == [str(bcp_2.id), str(bcp_1.id)]
    assert bcp["totales"] == {"PEN": "85.40", "USD": "20.00"}
    assert {i["id"] for i in agente_kasnet["items"]} == {str(kasnet.id), str(mia.id)}
    asi = {i["id"]: i for i in agente_kasnet["items"]}
    assert (asi[str(mia.id)]["en_ruta"], asi[str(kasnet.id)]["en_ruta"]) == (True, False)
    assert [i["id"] for i in ninguno["items"]] == [str(sin_lugar.id)]
    assert cuerpo["totales"] == {"PEN": "187.50", "USD": "20.00"}


def test_la_ruta_es_de_la_asistente(
    cliente: TestClient, db: Session, dos_gerentes: DosGerentes
) -> None:
    """El gerente no paga ni sube vouchers (TASK-109): la ruta le responde 403."""
    equipo = dos_gerentes.uno
    deuda = con_lugar(db, nueva_deuda(db, equipo.gerente), "agente_bcp")

    ver = cliente.get("/api/v1/ruta", headers=cabecera(equipo.gerente))
    iniciar = cliente.post(
        "/api/v1/ruta/iniciar", json={"deudas": [str(deuda.id)]}, headers=cabecera(equipo.gerente)
    )

    assert (ver.status_code, ver.json()["code"]) == (403, "SIN_PERMISO")
    assert (iniciar.status_code, iniciar.json()["code"]) == (403, "SIN_PERMISO")
    db.refresh(deuda)
    assert deuda.estado == "pendiente"


def test_iniciar_en_lote_da_el_resultado_de_cada_deuda_sin_omitir_ninguna(
    cliente: TestClient, db: Session, dos_gerentes: DosGerentes
) -> None:
    equipo = dos_gerentes.uno
    db.add(Limite(gerente_id=equipo.gerente.id, por_pago=100))
    dentro = nueva_deuda(db, equipo.gerente, "85.40")
    supera = nueva_deuda(db, equipo.gerente, "150.00")
    dolares = nueva_deuda(db, equipo.gerente, "20.00", "USD")
    de_otro = en_proceso_de(db, nueva_deuda(db, equipo.gerente, "30.00"), equipo.gerente)
    ajena = nueva_deuda(db, dos_gerentes.dos.gerente, "40.00")
    orden = [supera.id, ajena.id, dentro.id, de_otro.id, dolares.id]

    r = cliente.post(
        "/api/v1/ruta/iniciar",
        json={"deudas": [str(i) for i in orden]},
        headers=cabecera(equipo.asistente),
    )

    assert r.status_code == 200
    cuerpo = r.json()
    assert [x["deuda_id"] for x in cuerpo["resultados"]] == [str(i) for i in orden]
    assert [(x["resultado"], x["codigo"]) for x in cuerpo["resultados"]] == [
        ("requiere_aprobacion", None),
        ("conflicto", "NO_ENCONTRADO"),
        ("iniciada", None),
        ("conflicto", "PAGO_EN_CURSO"),
        ("requiere_aprobacion", None),
    ]
    assert cuerpo["totales"] == {"PEN": "85.40", "USD": "0.00"}
    # Un conflicto no deshace las demás.
    for deuda, estado in [
        (dentro, "en_proceso"),
        (supera, "esperando_aprobacion"),
        (dolares, "esperando_aprobacion"),
        (ajena, "pendiente"),
    ]:
        db.refresh(deuda)
        assert deuda.estado == estado

    # Repetir el lote no tiene efectos nuevos: la iniciada se informa repetida.
    otra = cliente.post(
        "/api/v1/ruta/iniciar",
        json={"deudas": [str(dentro.id)]},
        headers=cabecera(equipo.asistente),
    )
    assert otra.json()["resultados"][0] | {"mensaje": None} == {
        "deuda_id": str(dentro.id),
        "resultado": "iniciada",
        "codigo": None,
        "mensaje": None,
        "repetido": True,
    }

    # La que espera aprobación sigue en la ruta para que sepa por qué no puede iniciarla.
    ruta = cliente.get("/api/v1/ruta", headers=cabecera(equipo.asistente)).json()
    estados = {i["id"]: i["estado"] for g in ruta["grupos"] for i in g["items"]}
    assert estados[str(supera.id)] == "esperando_aprobacion"
    assert estados[str(dentro.id)] == "en_proceso"


@pytest.mark.parametrize(
    "deudas",
    [[], ["repetida", "repetida"], [str(uuid.uuid4()) for _ in range(51)]],
    ids=["vacia", "repetida", "mas_de_50"],
)
def test_lote_invalido_responde_422(
    cliente: TestClient, db: Session, dos_gerentes: DosGerentes, deudas: list[str]
) -> None:
    equipo = dos_gerentes.uno
    if deudas == ["repetida", "repetida"]:
        deuda_id = str(nueva_deuda(db, equipo.gerente).id)
        deudas = [deuda_id, deuda_id]

    r = cliente.post(
        "/api/v1/ruta/iniciar", json={"deudas": deudas}, headers=cabecera(equipo.asistente)
    )

    assert r.status_code == 422
    assert r.json()["code"] == "VALIDACION"


def test_marcar_pagada_deja_la_deuda_en_proceso_y_conserva_la_primera_fecha(
    cliente: TestClient, db: Session, dos_gerentes: DosGerentes
) -> None:
    equipo = dos_gerentes.uno
    deuda = con_lugar(db, nueva_deuda(db, equipo.gerente, "85.40"), "agente_bcp")
    ruta = f"/api/v1/deudas/{deuda.id}/marcar-pagada"

    sin_iniciar = cliente.post(ruta, headers=cabecera(equipo.asistente))
    assert (sin_iniciar.status_code, sin_iniciar.json()["code"]) == (409, "SIN_INTENTO")

    cliente.post(
        "/api/v1/ruta/iniciar", json={"deudas": [str(deuda.id)]}, headers=cabecera(equipo.asistente)
    )
    otro = cliente.post(ruta, headers=cabecera(equipo.gerente))
    assert (otro.status_code, otro.json()["code"]) == (409, "PAGO_EN_CURSO")

    r = cliente.post(ruta, headers=cabecera(equipo.asistente))
    assert r.status_code == 200
    cuerpo = r.json()
    assert (cuerpo["estado"], cuerpo["pago_realizado"], cuerpo["saldo"]) == (
        "en_proceso",
        True,
        "85.40",
    )
    assert cuerpo["pago_realizado_en"] is not None

    repetido = cliente.post(ruta, headers=cabecera(equipo.asistente))
    assert repetido.json()["pago_realizado_en"] == cuerpo["pago_realizado_en"]
    assert declaraciones(db, deuda) == 1

    # Declarada no se puede cancelar: falta su comprobante y sigue en la ruta como declarada.
    cancelar = cliente.post(
        f"/api/v1/deudas/{deuda.id}/cancelar-inicio", headers=cabecera(equipo.asistente)
    )
    assert (cancelar.status_code, cancelar.json()["code"]) == (409, "PAGO_DECLARADO")
    item = cliente.get("/api/v1/ruta", headers=cabecera(equipo.asistente)).json()["grupos"][0][
        "items"
    ][0]
    assert (item["id"], item["en_ruta"], item["pago_realizado"]) == (str(deuda.id), True, True)

    # Con el voucher subido sigue en su ruta, por validar, hasta que el gerente lo valide.
    db.refresh(deuda)
    nuevo_comprobante(
        db, deuda, equipo.asistente, "85.40", estado="procesando", creado_en=deuda.pago_iniciado_en
    )
    deuda.estado = "por_validar"
    db.flush()
    ruta = cliente.get("/api/v1/ruta", headers=cabecera(equipo.asistente)).json()
    item = ruta["grupos"][0]["items"][0]
    assert (item["estado"], item["en_ruta"], item["comprobante_estado"]) == (
        "por_validar",
        True,
        "procesando",
    )


def test_la_deuda_de_otro_gerente_responde_404(
    cliente: TestClient, db: Session, dos_gerentes: DosGerentes
) -> None:
    ajena = en_proceso_de(db, nueva_deuda(db, dos_gerentes.dos.gerente), dos_gerentes.dos.asistente)

    r = cliente.post(
        f"/api/v1/deudas/{ajena.id}/marcar-pagada", headers=cabecera(dos_gerentes.uno.asistente)
    )

    assert (r.status_code, r.json()["code"]) == (404, "NO_ENCONTRADO")
    db.refresh(ajena)
    assert ajena.pago_realizado is False


def test_sin_sesion_responde_401(cliente: TestClient) -> None:
    assert cliente.get("/api/v1/ruta").status_code == 401
    assert (
        cliente.post("/api/v1/ruta/iniciar", json={"deudas": [str(uuid.uuid4())]}).status_code
        == 401
    )
