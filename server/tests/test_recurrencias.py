"""Deudas recurrentes y recibos retrasados (H11 CA04 y CA05, TASK-39)."""

from collections.abc import Iterator
from datetime import date, datetime
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.tiempo import zona_horaria
from app.main import app
from app.models import Deuda, Notificacion, Recurrencia, Servicio, Usuario
from app.services.recurrencias import avisar_recibos_retrasados, generar_recurrentes
from tests.conftest import DosGerentes, nueva_categoria
from tests.test_api_comprobantes import cabecera

LIMA = zona_horaria()


def servicio_con(
    db: Session,
    gerente: Usuario,
    tipo: str = "monto_fijo",
    dia_emision: int | None = 5,
    dia_vencimiento: int = 20,
    creada: datetime = datetime(2026, 9, 10, tzinfo=LIMA),
) -> tuple[Servicio, Recurrencia]:
    servicio = Servicio(
        gerente_id=gerente.id,
        categoria_id=nueva_categoria(db, gerente, tipo).id,
        empresa_nombre="Movistar",
        codigo_suministro=f"R{id(creada)}{dia_vencimiento}{tipo}"[:20],
    )
    db.add(servicio)
    db.flush()
    recurrencia = Recurrencia(
        servicio_id=servicio.id,
        tipo="monto_fijo" if tipo == "monto_fijo" else "variable",
        monto=Decimal("129.90") if tipo == "monto_fijo" else None,
        dia_emision=dia_emision,
        dia_vencimiento=dia_vencimiento,
    )
    db.add(recurrencia)
    db.flush()
    recurrencia.creado_en = creada
    db.flush()
    return servicio, recurrencia


def deudas_de(db: Session, servicio: Servicio) -> list[Deuda]:
    return list(
        db.scalars(select(Deuda).where(Deuda.servicio_id == servicio.id).order_by(Deuda.periodo))
    )


def test_monto_fijo_crea_cada_mes_y_recupera_los_omitidos_sin_duplicar(
    db: Session, dos_gerentes: DosGerentes
) -> None:
    servicio, recurrencia = servicio_con(db, dos_gerentes.uno.gerente)
    hoy = datetime(2026, 11, 6, 0, 5, tzinfo=LIMA)

    assert generar_recurrentes(db, hoy) == 3
    assert generar_recurrentes(db, hoy) == 0

    deudas = deudas_de(db, servicio)
    assert [d.periodo for d in deudas] == [date(2026, 9, 1), date(2026, 10, 1), date(2026, 11, 1)]
    assert {(d.estado, d.monto, d.origen) for d in deudas} == {
        ("pendiente", Decimal("129.90"), "recurrente")
    }
    assert deudas[-1].fecha_vencimiento == date(2026, 11, 20)
    assert recurrencia.ultima_generacion == date(2026, 11, 1)


def test_variable_espera_su_recibo_sin_monto(db: Session, dos_gerentes: DosGerentes) -> None:
    servicio, _ = servicio_con(db, dos_gerentes.uno.gerente, tipo="servicio_variable")

    generar_recurrentes(db, datetime(2026, 9, 12, tzinfo=LIMA))

    (deuda,) = deudas_de(db, servicio)
    assert (deuda.estado, deuda.monto, deuda.fecha_estimada) == (
        "esperando_recibo",
        None,
        date(2026, 9, 5),
    )


def test_el_dia_que_no_existe_va_al_fin_de_mes_y_el_vencimiento_puede_ser_el_mes_siguiente(
    db: Session, dos_gerentes: DosGerentes
) -> None:
    fin_de_mes, _ = servicio_con(
        db,
        dos_gerentes.uno.gerente,
        dia_emision=1,
        dia_vencimiento=31,
        creada=datetime(2027, 2, 1, tzinfo=LIMA),
    )
    cruzado, _ = servicio_con(
        db,
        dos_gerentes.uno.gerente,
        dia_emision=25,
        dia_vencimiento=5,
        creada=datetime(2027, 2, 1, tzinfo=LIMA),
    )

    generar_recurrentes(db, datetime(2027, 2, 26, tzinfo=LIMA))

    assert deudas_de(db, fin_de_mes)[0].fecha_vencimiento == date(2027, 2, 28)
    assert deudas_de(db, cruzado)[0].fecha_vencimiento == date(2027, 3, 5)


def test_baja_inactiva_o_ya_registrada_no_genera(db: Session, dos_gerentes: DosGerentes) -> None:
    gerente = dos_gerentes.uno.gerente
    de_baja, _ = servicio_con(db, gerente)
    de_baja.estado = "baja"
    inactiva, recurrencia = servicio_con(db, gerente, dia_vencimiento=21)
    recurrencia.activa = False
    manual, _ = servicio_con(db, gerente, dia_vencimiento=22)
    db.add(
        Deuda(
            gerente_id=gerente.id,
            servicio_id=manual.id,
            periodo=date(2026, 9, 1),
            monto=Decimal("1.00"),
            estado="anulada",
            fecha_vencimiento=date(2026, 9, 22),
        )
    )
    db.flush()

    generar_recurrentes(db, datetime(2026, 9, 15, tzinfo=LIMA))

    assert deudas_de(db, de_baja) == [] and deudas_de(db, inactiva) == []
    assert [d.estado for d in deudas_de(db, manual)] == ["anulada"]


def test_el_recibo_retrasado_avisa_una_sola_vez(db: Session, dos_gerentes: DosGerentes) -> None:
    equipo = dos_gerentes.uno
    servicio_con(db, equipo.gerente, tipo="servicio_variable")
    generar_recurrentes(db, datetime(2026, 9, 6, tzinfo=LIMA))

    assert avisar_recibos_retrasados(db, datetime(2026, 9, 8, tzinfo=LIMA)) == 0
    assert avisar_recibos_retrasados(db, datetime(2026, 9, 9, tzinfo=LIMA)) == 2
    assert avisar_recibos_retrasados(db, datetime(2026, 9, 10, tzinfo=LIMA)) == 0
    avisos = db.scalars(select(Notificacion).where(Notificacion.titulo == "El recibo se retrasa"))
    assert {a.usuario_id for a in avisos} == {equipo.gerente.id, equipo.asistente.id}


@pytest.fixture
def cliente(db: Session) -> Iterator[TestClient]:
    app.dependency_overrides[get_db] = lambda: db
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_configurar_la_recurrencia_de_un_servicio(
    cliente: TestClient, db: Session, dos_gerentes: DosGerentes
) -> None:
    equipo = dos_gerentes.uno
    servicio = Servicio(
        gerente_id=equipo.gerente.id,
        categoria_id=nueva_categoria(db, equipo.gerente, "servicio_variable").id,
        empresa_nombre="Sedalib",
        codigo_suministro="SED-1",
    )
    db.add(servicio)
    db.flush()
    ruta = f"/api/v1/servicios/{servicio.id}/recurrencia"

    assert cliente.get(ruta, headers=cabecera(equipo.asistente)).status_code == 404
    r = cliente.put(
        ruta,
        headers=cabecera(equipo.asistente),
        json={"monto": "50.00", "dia_emision": 5, "dia_vencimiento": 20},
    )
    assert r.status_code == 200, r.json()
    assert (r.json()["tipo"], r.json()["monto"]) == ("variable", None)
    assert cliente.get(ruta, headers=cabecera(equipo.gerente)).json()["dia_vencimiento"] == 20

    ajeno = cliente.get(ruta, headers=cabecera(dos_gerentes.dos.gerente))
    assert (ajeno.status_code, ajeno.json()["code"]) == (404, "NO_ENCONTRADO")


def test_un_monto_fijo_exige_monto_y_un_prestamo_no_se_repite(
    cliente: TestClient, db: Session, dos_gerentes: DosGerentes
) -> None:
    gerente = dos_gerentes.uno.gerente
    for tipo, esperado in (("monto_fijo", "monto"), ("prestamo", "servicio_id")):
        servicio = Servicio(
            gerente_id=gerente.id,
            categoria_id=nueva_categoria(db, gerente, tipo).id,
            empresa_nombre="X",
            codigo_suministro=f"X-{tipo}",
        )
        db.add(servicio)
        db.flush()
        r = cliente.put(
            f"/api/v1/servicios/{servicio.id}/recurrencia",
            headers=cabecera(gerente),
            json={"dia_vencimiento": 10},
        )
        assert (r.status_code, r.json()["field"]) == (422, esperado)
