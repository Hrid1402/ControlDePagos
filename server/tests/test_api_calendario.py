"""Calendario por gerente, filtros, totales por moneda e importación ICS."""

from collections.abc import Iterator
from datetime import date, datetime
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from icalendar import Calendar
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.seguridad import crear_token
from app.core.tiempo import zona_horaria
from app.main import app
from app.models import Recurrencia, Servicio, Usuario
from app.services import calendario
from tests.conftest import DosGerentes, nueva_deuda

RUTA = "/api/v1/calendario"
RANGO = {"desde": "2026-10-01", "hasta": "2026-10-31"}


@pytest.fixture
def cliente(db: Session) -> Iterator[TestClient]:
    app.dependency_overrides[get_db] = lambda: db
    yield TestClient(app)
    app.dependency_overrides.clear()


def cabecera(usuario: Usuario) -> dict[str, str]:
    return {"Authorization": f"Bearer {crear_token(usuario)}"}


def test_agrupa_por_fecha_moneda_y_gerente(
    cliente: TestClient, db: Session, dos_gerentes: DosGerentes
) -> None:
    gerente = dos_gerentes.uno.gerente
    pen = nueva_deuda(db, gerente, "120.50", fecha_vencimiento=date(2026, 10, 25))
    usd = nueva_deuda(db, gerente, "40.00", moneda="USD", fecha_vencimiento=date(2026, 10, 25))
    nueva_deuda(db, dos_gerentes.dos.gerente, "999.00", fecha_vencimiento=date(2026, 10, 25))
    respuesta = cliente.get(RUTA, params=RANGO, headers=cabecera(dos_gerentes.uno.asistente))
    assert respuesta.status_code == 200
    dia = respuesta.json()["dias"][0]
    assert dia["fecha"] == "2026-10-25"
    assert {item["id"] for item in dia["deudas"]} == {str(pen.id), str(usd.id)}
    assert dia["totales_confirmados"] == {"PEN": "120.50", "USD": "40.00"}
    assert dia["totales_proyectados"] == {}


def test_filtros_estado_categoria_y_proyeccion(
    cliente: TestClient, db: Session, dos_gerentes: DosGerentes
) -> None:
    gerente = dos_gerentes.uno.gerente
    pendiente = nueva_deuda(db, gerente, "50.00", fecha_vencimiento=date(2026, 10, 28))
    sin_recibo = nueva_deuda(
        db, gerente, None, estado="esperando_recibo", fecha_vencimiento=date(2026, 10, 28)
    )
    db.add(
        Recurrencia(
            servicio_id=sin_recibo.servicio_id,
            tipo="monto_fijo",
            monto=Decimal("35.00"),
            dia_vencimiento=28,
        )
    )
    db.flush()
    respuesta = cliente.get(RUTA, params=RANGO, headers=cabecera(gerente))
    dia = respuesta.json()["dias"][0]
    assert dia["totales_confirmados"] == {"PEN": "50.00"}
    assert dia["totales_proyectados"] == {"PEN": "35.00"}
    assert {x["id"] for x in dia["deudas"]} == {str(pendiente.id), str(sin_recibo.id)}
    categoria_id = db.get_one(Servicio, pendiente.servicio_id).categoria_id
    respuesta = cliente.get(
        RUTA,
        params={**RANGO, "categoria": str(categoria_id), "estado": "esperando_recibo"},
        headers=cabecera(gerente),
    )
    assert respuesta.json()["dias"] == []


def test_ics_se_importa_y_excluye_pagadas(
    cliente: TestClient, db: Session, dos_gerentes: DosGerentes
) -> None:
    gerente = dos_gerentes.uno.gerente
    pendiente = nueva_deuda(db, gerente, "20.00", fecha_vencimiento=date(2026, 10, 31))
    nueva_deuda(db, gerente, "30.00", estado="pagada", fecha_vencimiento=date(2026, 10, 31))
    respuesta = cliente.get(f"{RUTA}/exportar.ics", params=RANGO, headers=cabecera(gerente))
    assert respuesta.status_code == 200
    assert respuesta.headers["content-type"].startswith("text/calendar")
    eventos = [x for x in Calendar.from_ical(respuesta.content).walk() if x.name == "VEVENT"]
    assert len(eventos) == 1
    assert str(eventos[0]["UID"]) == f"deuda-{pendiente.id}@control-de-pagos"
    assert eventos[0].decoded("DTSTART") == date(2026, 10, 31)
    assert eventos[0].decoded("DTEND") == date(2026, 11, 1)


def test_rango_invertido_rechazado(cliente: TestClient, dos_gerentes: DosGerentes) -> None:
    respuesta = cliente.get(
        RUTA,
        params={"desde": "2026-11-01", "hasta": "2026-10-01"},
        headers=cabecera(dos_gerentes.uno.gerente),
    )
    assert respuesta.status_code == 422
    assert respuesta.json()["field"] == "desde"


def test_vencida_es_la_misma_del_listado_y_la_bandeja(
    cliente: TestClient,
    db: Session,
    dos_gerentes: DosGerentes,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Vencida no es solo la pendiente: toda deuda no pagada ni anulada con el vencimiento ya
    pasado en Lima. Una que vence hoy todavía no está vencida."""
    monkeypatch.setattr(
        calendario, "ahora_lima", lambda: datetime(2026, 10, 20, 23, 30, tzinfo=zona_horaria())
    )
    gerente = dos_gerentes.uno.gerente
    vence = date(2026, 10, 15)
    parcial = nueva_deuda(db, gerente, estado="pagada_parcial", fecha_vencimiento=vence)
    sin_recibo = nueva_deuda(db, gerente, None, estado="esperando_recibo", fecha_vencimiento=vence)
    pagada = nueva_deuda(db, gerente, estado="pagada", fecha_vencimiento=vence)
    hoy = nueva_deuda(db, gerente, fecha_vencimiento=date(2026, 10, 20))

    dias = cliente.get(RUTA, params=RANGO, headers=cabecera(gerente)).json()["dias"]

    estados = {d["id"]: d["estado"] for dia in dias for d in dia["deudas"]}
    assert estados == {
        str(parcial.id): "vencida",
        str(sin_recibo.id): "vencida",
        str(pagada.id): "pagada",
        str(hoy.id): "pendiente",
    }
