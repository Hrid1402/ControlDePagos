"""Detalle de una deuda (H17, TASK-53): datos, abonos, comprobantes, historial, línea de tiempo y
acciones según estado y rol."""

import uuid
from collections.abc import Iterator
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.main import app
from app.models import HistorialMonto
from tests.conftest import DosGerentes, nueva_deuda, nuevo_comprobante
from tests.test_api_comprobantes import cabecera


@pytest.fixture
def cliente(db: Session) -> Iterator[TestClient]:
    app.dependency_overrides[get_db] = lambda: db
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_muestra_abonos_comprobantes_historial_y_linea_de_tiempo(
    cliente: TestClient, db: Session, dos_gerentes: DosGerentes
) -> None:
    equipo = dos_gerentes.uno
    deuda = nueva_deuda(db, equipo.gerente, monto="100.00", estado="pagada_parcial")
    validado = nuevo_comprobante(db, deuda, equipo.asistente, "40.00", estado="validado")
    nuevo_comprobante(db, deuda, equipo.asistente, "60.00", estado="rechazado")
    db.add(
        HistorialMonto(
            deuda_id=deuda.id,
            monto_anterior=Decimal("90.00"),
            monto_nuevo=Decimal("100.00"),
            origen="manual",
            usuario_id=equipo.gerente.id,
        )
    )
    db.flush()

    r = cliente.get(f"/api/v1/deudas/{deuda.id}", headers=cabecera(equipo.asistente))

    assert r.status_code == 200, r.json()
    cuerpo = r.json()
    assert (cuerpo["monto"], cuerpo["pagado"], cuerpo["saldo"]) == ("100.00", "40.00", "60.00")
    assert cuerpo["servicio"]["empresa"] == "Hidrandina"
    assert {c["estado"] for c in cuerpo["comprobantes"]} == {"validado", "rechazado"}
    assert cuerpo["historial_montos"][0]["monto_anterior"] == "90.00"
    tipos = [e["tipo"] for e in cuerpo["linea_tiempo"]]
    assert "deuda_creada" in tipos and "comprobante_validado" in tipos
    evento = next(e for e in cuerpo["linea_tiempo"] if e["tipo"] == "comprobante_validado")
    assert (evento["actor"], evento["detalle"]["comprobante_id"]) == (None, str(validado.id))
    assert cuerpo["acciones"] == ["iniciar_pago", "comentar"]


def test_en_proceso_ofrece_adjuntar_y_cancelar_a_quien_paga(
    cliente: TestClient, db: Session, dos_gerentes: DosGerentes
) -> None:
    equipo = dos_gerentes.uno
    deuda = nueva_deuda(db, equipo.gerente, estado="en_proceso")
    deuda.pago_iniciado_por = equipo.asistente.id
    db.flush()

    r = cliente.get(f"/api/v1/deudas/{deuda.id}", headers=cabecera(equipo.asistente))

    cuerpo = r.json()
    assert cuerpo["acciones"] == ["cancelar_inicio", "adjuntar_comprobante", "comentar"]
    assert cuerpo["en_proceso"]["rol"] == "asistente"


def test_una_deuda_anulada_es_de_solo_lectura(
    cliente: TestClient, db: Session, dos_gerentes: DosGerentes
) -> None:
    deuda = nueva_deuda(db, dos_gerentes.uno.gerente, estado="anulada")

    r = cliente.get(f"/api/v1/deudas/{deuda.id}", headers=cabecera(dos_gerentes.uno.gerente))

    assert r.json()["acciones"] == []


def test_la_deuda_de_otro_gerente_responde_404(
    cliente: TestClient, db: Session, dos_gerentes: DosGerentes
) -> None:
    ajena = nueva_deuda(db, dos_gerentes.dos.gerente)

    for deuda_id in (ajena.id, uuid.uuid4()):
        r = cliente.get(f"/api/v1/deudas/{deuda_id}", headers=cabecera(dos_gerentes.uno.asistente))
        assert (r.status_code, r.json()["code"]) == (404, "NO_ENCONTRADO")
