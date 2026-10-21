"""Edición, anulación y préstamos (H11 CA05, CA07, CA10 y CA11; TASK-40)."""

import uuid
from collections.abc import Iterator
from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.main import app
from app.models import Deuda, HistorialMonto, Notificacion, Servicio
from tests.conftest import DosGerentes, nueva_categoria, nueva_deuda, nuevo_comprobante
from tests.test_api_comprobantes import cabecera


@pytest.fixture
def cliente(db: Session) -> Iterator[TestClient]:
    app.dependency_overrides[get_db] = lambda: db
    yield TestClient(app)
    app.dependency_overrides.clear()


def editar(cliente: TestClient, usuario: object, deuda_id: uuid.UUID, cuerpo: dict) -> object:
    return cliente.put(f"/api/v1/deudas/{deuda_id}", headers=cabecera(usuario), json=cuerpo)  # type: ignore[arg-type]


def test_confirmar_el_monto_del_recibo_deja_la_deuda_pendiente(
    cliente: TestClient, db: Session, dos_gerentes: DosGerentes
) -> None:
    deuda = nueva_deuda(db, dos_gerentes.uno.gerente, monto=None, estado="esperando_recibo")

    r = editar(cliente, dos_gerentes.uno.asistente, deuda.id, {"monto": "92.30"})

    assert r.status_code == 200, r.json()  # type: ignore[attr-defined]
    assert (r.json()["estado"], r.json()["monto"]) == ("pendiente", "92.30")  # type: ignore[attr-defined]
    assert db.scalar(select(HistorialMonto).where(HistorialMonto.deuda_id == deuda.id)) is None


def test_cambiar_el_monto_guarda_el_historial_y_avisa_a_la_asistente(
    cliente: TestClient, db: Session, dos_gerentes: DosGerentes
) -> None:
    equipo = dos_gerentes.uno
    deuda = nueva_deuda(db, equipo.gerente, monto="100.00")

    r = editar(cliente, equipo.gerente, deuda.id, {"monto": "120.00", "numero_recibo": "F1-9"})

    cuerpo = r.json()  # type: ignore[attr-defined]
    assert cuerpo["historial_montos"][0]["monto_anterior"] == "100.00"
    assert cuerpo["linea_tiempo"][0]["tipo"] == "deuda_monto_cambiado"
    aviso = db.scalar(select(Notificacion).where(Notificacion.usuario_id == equipo.asistente.id))
    assert aviso is not None and "a PEN 120.00" in aviso.mensaje


def test_monto_y_moneda_no_cambian_con_un_pago_en_curso_ni_bajo_lo_abonado(
    cliente: TestClient, db: Session, dos_gerentes: DosGerentes
) -> None:
    equipo = dos_gerentes.uno
    en_curso = nueva_deuda(db, equipo.gerente, estado="en_proceso")
    r = editar(cliente, equipo.gerente, en_curso.id, {"monto": "1.00"})
    assert (r.status_code, r.json()["code"]) == (409, "PAGO_EN_CURSO")  # type: ignore[attr-defined]
    assert editar(cliente, equipo.gerente, en_curso.id, {"numero_recibo": "A1"}).status_code == 200  # type: ignore[attr-defined]

    abonada = nueva_deuda(db, equipo.gerente, monto="100.00", estado="pagada_parcial")
    nuevo_comprobante(db, abonada, equipo.asistente, "40.00", estado="validado")
    assert editar(cliente, equipo.gerente, abonada.id, {"moneda": "USD"}).status_code == 409  # type: ignore[attr-defined]
    assert editar(cliente, equipo.gerente, abonada.id, {"monto": "39.99"}).status_code == 422  # type: ignore[attr-defined]
    r = editar(cliente, equipo.gerente, abonada.id, {"monto": "40.00"})
    assert r.json()["estado"] == "pagada"  # type: ignore[attr-defined]


def test_anular_es_del_gerente_y_no_con_abonos(
    cliente: TestClient, db: Session, dos_gerentes: DosGerentes
) -> None:
    equipo = dos_gerentes.uno
    deuda = nueva_deuda(db, equipo.gerente)
    ruta = f"/api/v1/deudas/{deuda.id}/anular"

    assert cliente.post(ruta, headers=cabecera(equipo.asistente)).status_code == 403
    r = cliente.post(ruta, headers=cabecera(equipo.gerente), json={"motivo": "Duplicada"})
    assert (r.json()["estado"], r.json()["acciones"]) == ("anulada", [])
    assert cliente.post(ruta, headers=cabecera(equipo.gerente)).status_code == 200

    abonada = nueva_deuda(db, equipo.gerente, estado="pagada_parcial")
    nuevo_comprobante(db, abonada, equipo.asistente, "10.00", estado="validado")
    r = cliente.post(f"/api/v1/deudas/{abonada.id}/anular", headers=cabecera(equipo.gerente))
    assert (r.status_code, r.json()["code"]) == (409, "CON_ABONOS")


def test_un_prestamo_genera_su_cronograma_exacto(
    cliente: TestClient, db: Session, dos_gerentes: DosGerentes
) -> None:
    equipo = dos_gerentes.uno
    servicio = Servicio(
        gerente_id=equipo.gerente.id,
        categoria_id=nueva_categoria(db, equipo.gerente, "prestamo").id,
        empresa_nombre="BCP",
        codigo_suministro="PR-1",
    )
    db.add(servicio)
    db.flush()
    cuerpo = {
        "servicio_id": str(servicio.id),
        "monto_total": "100.00",
        "cuotas_total": 3,
        "fecha_primera_cuota": "2027-01-31",
    }

    r = cliente.post("/api/v1/prestamos", headers=cabecera(equipo.asistente), json=cuerpo)

    assert r.status_code == 201, r.json()
    cuotas = r.json()["cuotas"]
    assert [c["monto"] for c in cuotas] == ["33.33", "33.33", "33.34"]
    assert [c["fecha_vencimiento"] for c in cuotas] == ["2027-01-31", "2027-02-28", "2027-03-31"]
    deudas = list(db.scalars(select(Deuda).where(Deuda.servicio_id == servicio.id)))
    assert sum((d.monto or Decimal(0) for d in deudas), Decimal(0)) == Decimal("100.00")
    assert {d.periodo for d in deudas} == {date(2027, 1, 1), date(2027, 2, 1), date(2027, 3, 1)}

    repetido = cliente.post("/api/v1/prestamos", headers=cabecera(equipo.gerente), json=cuerpo)
    assert (repetido.status_code, repetido.json()["code"]) == (409, "DUPLICADO")


def test_un_servicio_que_no_es_prestamo_no_admite_cuotas(
    cliente: TestClient, db: Session, dos_gerentes: DosGerentes
) -> None:
    deuda = nueva_deuda(db, dos_gerentes.uno.gerente)
    cuerpo = {
        "servicio_id": str(deuda.servicio_id),
        "monto_total": "100.00",
        "cuotas_total": 2,
        "fecha_primera_cuota": "2027-01-10",
    }

    r = cliente.post("/api/v1/prestamos", headers=cabecera(dos_gerentes.uno.gerente), json=cuerpo)

    assert (r.status_code, r.json()["field"]) == (422, "servicio_id")
