"""Historial de acciones de punta a punta (H34, TASK-20).

Cada acción de CA02 se hace por la API, como la haría el usuario, y se busca su registro en el
historial del gerente. Completa test_auditoria.py (servicio) y test_api_auditoria.py (filtros y
Excel): aquí se prueba que las rutas reales registran y que el historial no se edita por la API.
"""

from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.seguridad import crear_token, hashear_contrasena
from app.main import app
from app.models import Usuario
from tests.conftest import DosGerentes, nueva_deuda

AGENTE = "Mozilla/5.0 (Linux; Android 14) Chrome/141.0 Mobile Safari/537.36"
IP = "203.0.113.25"
CONTRASENA = "Clave-segura-1"


@pytest.fixture
def cliente(db: Session) -> Iterator[TestClient]:
    app.dependency_overrides[get_db] = lambda: db
    yield TestClient(app, client=(IP, 50000), headers={"User-Agent": AGENTE})
    app.dependency_overrides.clear()


def cabecera(usuario: Usuario) -> dict[str, str]:
    return {"Authorization": f"Bearer {crear_token(usuario)}"}


def historial(cliente: TestClient, gerente: Usuario, **filtros: str) -> list[dict[str, Any]]:
    r = cliente.get("/api/v1/auditoria", params={**filtros, "size": 100}, headers=cabecera(gerente))
    assert r.status_code == 200, r.text
    items: list[dict[str, Any]] = r.json()["items"]
    return items


def con_contrasena(db: Session, usuario: Usuario) -> Usuario:
    usuario.password_hash = hashear_contrasena(CONTRASENA)
    db.flush()
    return usuario


def test_ca01_ca02_el_ingreso_exitoso_registra_quien_cuando_y_desde_donde(
    cliente: TestClient, db: Session, dos_gerentes: DosGerentes
) -> None:
    equipo = dos_gerentes.uno
    asistente = con_contrasena(db, equipo.asistente)

    r = cliente.post(
        "/api/v1/auth/login", json={"username": asistente.username, "contrasena": CONTRASENA}
    )
    assert r.status_code == 200, r.text

    (ingreso,) = historial(cliente, equipo.gerente, accion="login_exitoso")
    assert ingreso["usuario_id"] == str(asistente.id)
    assert ingreso["usuario_nombre"] == asistente.username
    assert (ingreso["dispositivo"], ingreso["ip"]) == (AGENTE, IP)
    assert ingreso["creado_en"] is not None


def test_ca02_el_ingreso_fallido_de_una_cuenta_conocida_queda_en_su_historial(
    cliente: TestClient, db: Session, dos_gerentes: DosGerentes
) -> None:
    equipo = dos_gerentes.uno
    asistente = con_contrasena(db, equipo.asistente)

    r = cliente.post(
        "/api/v1/auth/login", json={"username": asistente.username, "contrasena": "Otra-clave-9"}
    )
    assert r.status_code == 401

    (fallido,) = historial(cliente, equipo.gerente, accion="login_fallido")
    assert fallido["usuario_id"] == str(asistente.id)
    assert "Otra-clave-9" not in str(fallido["detalle"])
    # El otro gerente no ve el intento.
    assert historial(cliente, dos_gerentes.dos.gerente, accion="login_fallido") == []


def test_ca02_crear_activar_desactivar_y_eliminar_una_cuenta_se_registran(
    cliente: TestClient, db: Session, dos_gerentes: DosGerentes
) -> None:
    gerente = dos_gerentes.uno.gerente
    creada = cliente.post(
        "/api/v1/asistentes",
        json={"nombres": "Teresa", "apellidos": "Huamán"},
        headers=cabecera(gerente),
    )
    assert creada.status_code == 201, creada.text
    nueva = creada.json()["id"]
    anterior = str(dos_gerentes.uno.asistente.id)

    for paso in ("activar", "desactivar"):
        r = cliente.post(f"/api/v1/asistentes/{nueva}/{paso}", headers=cabecera(gerente))
        assert r.status_code == 200, r.text
    assert cliente.delete(f"/api/v1/asistentes/{nueva}", headers=cabecera(gerente)).is_success

    sobre_la_nueva = [
        (r["accion"], r["usuario_id"])
        for r in reversed(historial(cliente, gerente))
        if r["entidad_id"] == nueva
    ]
    assert sobre_la_nueva == [
        ("cuenta_creada", str(gerente.id)),
        ("cuenta_activada", str(gerente.id)),
        ("cuenta_desactivada", str(gerente.id)),
        ("cuenta_eliminada", str(gerente.id)),
    ]
    # Activar a la nueva desactivó a la que estaba activa: también queda registrado.
    assert any(
        r["accion"] == "cuenta_desactivada" and r["entidad_id"] == anterior
        for r in historial(cliente, gerente)
    )
    eliminada = historial(cliente, gerente, accion="cuenta_eliminada")[0]
    assert eliminada["detalle"]["nombre"] == "Teresa Huamán"


def test_ca02_los_cambios_de_estado_de_una_deuda_se_registran_con_el_anterior_y_el_nuevo(
    cliente: TestClient, db: Session, dos_gerentes: DosGerentes
) -> None:
    equipo = dos_gerentes.uno
    deuda = nueva_deuda(db, equipo.gerente, monto="85.40")

    iniciar = cliente.post(
        f"/api/v1/deudas/{deuda.id}/iniciar-pago", headers=cabecera(equipo.asistente)
    )
    cancelar = cliente.post(
        f"/api/v1/deudas/{deuda.id}/cancelar-inicio", headers=cabecera(equipo.asistente)
    )
    assert (iniciar.status_code, cancelar.status_code) == (200, 200)

    (inicio,) = historial(cliente, equipo.gerente, accion="pago_iniciado")
    (cancelacion,) = historial(cliente, equipo.gerente, accion="pago_inicio_cancelado")
    assert inicio["entidad_id"] == cancelacion["entidad_id"] == str(deuda.id)
    assert inicio["usuario_id"] == str(equipo.asistente.id)
    assert inicio["detalle"]["estado_anterior"] == "pendiente"
    assert cancelacion["detalle"]["estado_nuevo"] == "pendiente"
