"""Revocación de una asistente con la sesión abierta en tiempo real (TASK-16, H03 CA13 y CA16).

test_asistentes_gestion.py comprueba que se publica el aviso de cierre; aquí la asistente tiene
un WebSocket real abierto, como en test_tiempo_real.py, y la acción del gerente se hace con los
servicios de TASK-14.
"""

import threading
from collections.abc import Iterator
from contextlib import contextmanager

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from starlette.testclient import WebSocketTestSession
from starlette.websockets import WebSocketDisconnect

from app.core.conexiones import CIERRE_NO_AUTENTICADO
from app.core.dependencias import Origen, obtener_fabrica_sesiones
from app.core.eventos import TipoEvento
from app.core.seguridad import crear_token
from app.main import app
from app.services.asistentes import (
    activar_asistente,
    desactivar_asistente,
    restablecer_contrasena_asistente,
)
from tests.conftest import DosGerentes, nueva_deuda, nueva_orden
from tests.test_asistentes_gestion import nueva_asistente

RUTA = "/api/v1/ws"
ORIGEN = Origen(dispositivo="pruebas", ip=None)


@pytest.fixture
def candado() -> threading.Lock:
    return threading.Lock()


@pytest.fixture
def cliente(db: Session, candado: threading.Lock) -> Iterator[TestClient]:
    # El server valida en otro hilo con la misma sesión de la prueba: el candado evita usarla
    # mientras el servicio del gerente hace commit.
    @contextmanager
    def sesion_compartida() -> Iterator[Session]:
        with candado:
            yield db

    app.dependency_overrides[obtener_fabrica_sesiones] = lambda: sesion_compartida
    # Con "with" corre el ciclo de vida: el suscriptor real de Redis queda escuchando.
    with TestClient(app) as cliente:
        yield cliente
    app.dependency_overrides.clear()


def autenticar(ws: WebSocketTestSession, token: str) -> None:
    ws.send_json({"tipo": "autenticar", "token": token})
    assert ws.receive_json()["tipo"] == TipoEvento.CONECTADO


def esperar_cierre(ws: WebSocketTestSession) -> WebSocketDisconnect:
    with pytest.raises(WebSocketDisconnect) as cierre:
        ws.receive_json()
    return cierre.value


def test_ca13_desactivar_cierra_al_instante_la_sesion_abierta_y_avisa_al_gerente(
    cliente: TestClient, db: Session, candado: threading.Lock, dos_gerentes: DosGerentes
) -> None:
    gerente = dos_gerentes.uno.gerente
    asistente = dos_gerentes.uno.asistente
    nueva_orden(db, nueva_deuda(db, gerente), "vista", asistente=asistente)
    with (
        cliente.websocket_connect(RUTA) as ws_asistente,
        cliente.websocket_connect(RUTA) as ws_gerente,
    ):
        autenticar(ws_asistente, crear_token(asistente))
        autenticar(ws_gerente, crear_token(gerente))

        with candado:
            desactivar_asistente(db, gerente, asistente.id, ORIGEN)

        evento = ws_asistente.receive_json()
        cierre = esperar_cierre(ws_asistente)
        # La sesión del gerente sigue abierta y recibe el aviso de la orden cancelada (CA14).
        aviso = ws_gerente.receive_json()
    assert (evento["tipo"], evento["datos"]) == ("sesion_cerrada", {"code": "CUENTA_INACTIVA"})
    assert (cierre.code, cierre.reason) == (CIERRE_NO_AUTENTICADO, "CUENTA_INACTIVA")
    assert aviso["tipo"] == TipoEvento.NOTIFICACION


def test_activar_a_otra_cierra_la_sesion_abierta_de_la_anterior(
    cliente: TestClient, db: Session, candado: threading.Lock, dos_gerentes: DosGerentes
) -> None:
    gerente = dos_gerentes.uno.gerente
    anterior = dos_gerentes.uno.asistente
    nueva = nueva_asistente(db, gerente, "Nueva")
    token_anterior = crear_token(anterior)
    with cliente.websocket_connect(RUTA) as ws:
        autenticar(ws, token_anterior)

        with candado:
            activar_asistente(db, gerente, nueva.id, ORIGEN)

        evento = ws.receive_json()
        cierre = esperar_cierre(ws)
    assert evento["tipo"] == "sesion_cerrada"
    assert cierre.reason == "CUENTA_INACTIVA"

    # La anterior no puede volver a conectarse; la nueva, ya activa, sí.
    with cliente.websocket_connect(RUTA) as ws:
        ws.send_json({"tipo": "autenticar", "token": token_anterior})
        assert esperar_cierre(ws).reason == "CUENTA_INACTIVA"
    with cliente.websocket_connect(RUTA) as ws:
        autenticar(ws, crear_token(nueva))


def test_ca16_restablecer_cierra_la_sesion_abierta_sin_desactivar_la_cuenta(
    cliente: TestClient, db: Session, candado: threading.Lock, dos_gerentes: DosGerentes
) -> None:
    gerente = dos_gerentes.uno.gerente
    asistente = dos_gerentes.uno.asistente
    with cliente.websocket_connect(RUTA) as ws:
        autenticar(ws, crear_token(asistente))

        with candado:
            restablecer_contrasena_asistente(db, gerente, asistente.id, ORIGEN)

        evento = ws.receive_json()
        cierre = esperar_cierre(ws)
    assert evento["datos"] == {"code": "SESION_REVOCADA"}
    assert (cierre.code, cierre.reason) == (CIERRE_NO_AUTENTICADO, "SESION_REVOCADA")

    # Con un token nuevo vuelve a conectarse: la cuenta sigue activa.
    with cliente.websocket_connect(RUTA) as ws:
        autenticar(ws, crear_token(asistente))
