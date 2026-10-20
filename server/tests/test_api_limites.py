"""API de límites y consumo del mes (H05, TASK-23).

CA01 a CA05, CA11 y CA12 por la API: definir los límites, verlos con el consumo PEN del mes y
que el inicio de pago los aplique a la asistente.
"""

from collections.abc import Iterator
from datetime import timedelta
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencias import Origen
from app.core.seguridad import crear_token
from app.core.tiempo import ahora_lima
from app.main import app
from app.models import Auditoria, SolicitudAprobacion, Usuario
from app.services.pagos import iniciar_pago
from tests.conftest import DosGerentes, nueva_deuda, nuevo_comprobante

URL = "/api/v1/limites"
ORIGEN = Origen(dispositivo="pruebas", ip=None)


@pytest.fixture
def cliente(db: Session) -> Iterator[TestClient]:
    app.dependency_overrides[get_db] = lambda: db
    yield TestClient(app)
    app.dependency_overrides.clear()


def cabecera(usuario: Usuario) -> dict[str, str]:
    return {"Authorization": f"Bearer {crear_token(usuario)}"}


def definir(cliente: TestClient, gerente: Usuario, **cuerpo: Any) -> Any:
    return cliente.put(URL, json=cuerpo, headers=cabecera(gerente))


def cambios_auditados(db: Session, gerente: Usuario) -> list[dict[str, Any]]:
    return list(
        db.scalars(
            select(Auditoria.detalle)
            .where(
                Auditoria.gerente_id == gerente.id,
                Auditoria.accion == "limites_actualizados",
            )
            .order_by(Auditoria.creado_en, Auditoria.id)
        )
    )


def test_ca03_ca04_sin_configurar_no_hay_limite_y_el_consumo_es_cero(
    cliente: TestClient, dos_gerentes: DosGerentes
) -> None:
    r = cliente.get(URL, headers=cabecera(dos_gerentes.uno.gerente))

    assert r.status_code == 200
    assert r.json() == {
        "por_pago": None,
        "mensual": None,
        "actualizado_en": None,
        "mes": ahora_lima().strftime("%Y-%m"),
        "consumo": {"validado": "0", "reservado": "0", "total": "0"},
    }


def test_ca01_ca02_definir_los_limites_los_guarda_y_queda_en_el_historial(
    cliente: TestClient, db: Session, dos_gerentes: DosGerentes
) -> None:
    gerente = dos_gerentes.uno.gerente

    r = definir(cliente, gerente, por_pago="250.50", mensual="2000")

    assert r.status_code == 200, r.text
    assert (r.json()["por_pago"], r.json()["mensual"]) == ("250.50", "2000.00")
    assert r.json()["actualizado_en"] is not None
    assert cliente.get(URL, headers=cabecera(gerente)).json()["mensual"] == "2000.00"
    assert cambios_auditados(db, gerente) == [
        {
            "por_pago": {"anterior": None, "nuevo": "250.50"},
            "mensual": {"anterior": None, "nuevo": "2000.00"},
        }
    ]
    # Guardar lo mismo otra vez no deja otro registro.
    definir(cliente, gerente, por_pago="250.5", mensual="2000.00")
    assert len(cambios_auditados(db, gerente)) == 1


def test_ca03_un_limite_vacio_quita_ese_limite(
    cliente: TestClient, db: Session, dos_gerentes: DosGerentes
) -> None:
    gerente = dos_gerentes.uno.gerente
    definir(cliente, gerente, por_pago="100", mensual="500")

    r = definir(cliente, gerente, por_pago=None, mensual="500")
    sin_cuerpo = definir(cliente, gerente)

    assert (r.json()["por_pago"], r.json()["mensual"]) == (None, "500.00")
    assert (sin_cuerpo.json()["por_pago"], sin_cuerpo.json()["mensual"]) == (None, None)


@pytest.mark.parametrize(
    ("cuerpo", "campo"),
    [
        ({"por_pago": "10.123"}, "por_pago"),
        ({"mensual": "0"}, "mensual"),
        ({"por_pago": "-5"}, "por_pago"),
        ({"mensual": "12345678901.00"}, "mensual"),
        ({"por_pago": "abc"}, "por_pago"),
    ],
)
def test_ca02_montos_invalidos_marcan_su_campo_y_no_cambian_nada(
    cliente: TestClient, db: Session, dos_gerentes: DosGerentes, cuerpo: dict[str, str], campo: str
) -> None:
    gerente = dos_gerentes.uno.gerente
    definir(cliente, gerente, por_pago="100", mensual="500")

    r = definir(cliente, gerente, **cuerpo)

    assert (r.status_code, r.json()["field"]) == (422, campo)
    actual = cliente.get(URL, headers=cabecera(gerente)).json()
    assert (actual["por_pago"], actual["mensual"]) == ("100.00", "500.00")


def test_ca02_el_limite_por_pago_no_supera_al_mensual(
    cliente: TestClient, dos_gerentes: DosGerentes
) -> None:
    r = definir(cliente, dos_gerentes.uno.gerente, por_pago="600", mensual="400")
    assert (r.status_code, r.json()["code"], r.json()["field"]) == (
        400,
        "LIMITE_INVALIDO",
        "por_pago",
    )


def test_ca04_ca05_ca11_el_consumo_separa_validado_y_en_proceso(
    cliente: TestClient, db: Session, dos_gerentes: DosGerentes
) -> None:
    equipo = dos_gerentes.uno
    # Validado este mes por la asistente: cuenta.
    nuevo_comprobante(
        db, nueva_deuda(db, equipo.gerente, monto="300.00"), equipo.asistente, "120.00"
    )
    # Del mes pasado: el límite mensual se reinicia el día 1 y ya no cuenta (CA11).
    nuevo_comprobante(
        db,
        nueva_deuda(db, equipo.gerente, monto="90.00"),
        equipo.asistente,
        "90.00",
        creado_en=ahora_lima().replace(day=1) - timedelta(days=2),
    )
    # Lo que paga el gerente no tiene límite y no consume el de la asistente (CA05).
    nuevo_comprobante(db, nueva_deuda(db, equipo.gerente, monto="500.00"), equipo.gerente, "500.00")
    # En proceso por la asistente: reservado. En dólares: no se suma a los soles.
    iniciar_pago(
        db, equipo.asistente, nueva_deuda(db, equipo.gerente, monto="80.50").id, origen=ORIGEN
    )
    nueva_deuda(db, equipo.gerente, monto="40.00", moneda="USD", estado="en_proceso")

    consumo = cliente.get(URL, headers=cabecera(equipo.gerente)).json()["consumo"]

    assert consumo == {"validado": "120.00", "reservado": "80.50", "total": "200.50"}
    otro = cliente.get(URL, headers=cabecera(dos_gerentes.dos.gerente)).json()["consumo"]
    assert otro["total"] == "0"


def test_ca01_el_inicio_de_pago_aplica_los_limites_definidos_por_la_api(
    cliente: TestClient, db: Session, dos_gerentes: DosGerentes
) -> None:
    equipo = dos_gerentes.uno
    definir(cliente, equipo.gerente, por_pago="100", mensual="150")

    dentro = cliente.post(
        f"/api/v1/deudas/{nueva_deuda(db, equipo.gerente, monto='90.00').id}/iniciar-pago",
        headers=cabecera(equipo.asistente),
    )
    por_pago = cliente.post(
        f"/api/v1/deudas/{nueva_deuda(db, equipo.gerente, monto='120.00').id}/iniciar-pago",
        headers=cabecera(equipo.asistente),
    )
    mensual = cliente.post(
        f"/api/v1/deudas/{nueva_deuda(db, equipo.gerente, monto='70.00').id}/iniciar-pago",
        headers=cabecera(equipo.asistente),
    )
    gerente = cliente.post(
        f"/api/v1/deudas/{nueva_deuda(db, equipo.gerente, monto='900.00').id}/iniciar-pago",
        headers=cabecera(equipo.gerente),
    )

    assert dentro.json()["resultado"] == "iniciado"
    assert por_pago.json()["resultado"] == "requiere_aprobacion"
    # 90 reservados + 70 superan los 150 del mes.
    assert mensual.json()["resultado"] == "requiere_aprobacion"
    assert gerente.json()["resultado"] == "iniciado"
    assert cliente.get(URL, headers=cabecera(equipo.gerente)).json()["consumo"]["reservado"] == (
        "90.00"
    )


def test_ca12_cambiar_un_limite_no_afecta_las_solicitudes_ya_enviadas(
    cliente: TestClient, db: Session, dos_gerentes: DosGerentes
) -> None:
    equipo = dos_gerentes.uno
    definir(cliente, equipo.gerente, por_pago="100")
    deuda = nueva_deuda(db, equipo.gerente, monto="250.00")
    pedida = iniciar_pago(db, equipo.asistente, deuda.id, origen=ORIGEN).solicitud
    assert pedida is not None

    definir(cliente, equipo.gerente, por_pago="500")
    definir(cliente, equipo.gerente, por_pago="50")

    db.refresh(pedida)
    assert (pedida.estado, pedida.monto) == ("pendiente", Decimal("250.00"))
    assert db.scalar(select(func.count()).select_from(SolicitudAprobacion)) == 1


def test_solo_el_gerente_ve_y_cambia_sus_limites(
    cliente: TestClient, dos_gerentes: DosGerentes
) -> None:
    definir(cliente, dos_gerentes.uno.gerente, por_pago="100")
    asistente = dos_gerentes.uno.asistente

    for respuesta in (
        cliente.get(URL, headers=cabecera(asistente)),
        cliente.put(URL, json={"por_pago": "900"}, headers=cabecera(asistente)),
    ):
        assert (respuesta.status_code, respuesta.json()["code"]) == (403, "SIN_PERMISO")
    assert cliente.get(URL).status_code == 401
    assert cliente.get(URL, headers=cabecera(dos_gerentes.dos.gerente)).json()["por_pago"] is None
    assert cliente.get(URL, headers=cabecera(dos_gerentes.uno.gerente)).json()["por_pago"] == (
        "100.00"
    )
