import asyncio
import json
import logging
import threading
import time
import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
import pytest
import redis
import redis.asyncio
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session
from starlette.testclient import WebSocketTestSession
from starlette.websockets import WebSocketDisconnect

from app.api.v1 import tiempo_real
from app.core import conexiones
from app.core.conexiones import (
    CIERRE_NO_AUTENTICADO,
    GestorConexiones,
    detener_suscriptor,
    escuchar,
    iniciar_suscriptor,
)
from app.core.config import settings
from app.core.dependencias import obtener_fabrica_sesiones
from app.core.eventos import Evento, TipoEvento, avisar_cierre_sesion, publicar
from app.core.seguridad import crear_token
from app.main import app
from app.models import Notificacion, Usuario
from app.services.notificaciones import TipoNotificacion, notificar
from tests.conftest import DosGerentes

RUTA = "/api/v1/ws"


@pytest.fixture
def candado() -> threading.Lock:
    return threading.Lock()


@pytest.fixture
def cliente(db: Session, candado: threading.Lock) -> Iterator[TestClient]:
    # El server valida en otro hilo con la misma sesión de la prueba (sus datos no están
    # confirmados en la base): el candado evita usarla mientras la prueba hace commit.
    @contextmanager
    def sesion_compartida() -> Iterator[Session]:
        with candado:
            yield db

    app.dependency_overrides[obtener_fabrica_sesiones] = lambda: sesion_compartida
    # Con "with" corre el ciclo de vida: el suscriptor real de Redis queda escuchando.
    with TestClient(app) as cliente:
        yield cliente
    app.dependency_overrides.clear()


@pytest.fixture
def confirmar(db: Session, candado: threading.Lock) -> Callable[[], None]:
    def commit() -> None:
        with candado:
            db.commit()

    return commit


def autenticar(ws: WebSocketTestSession, token: str) -> None:
    ws.send_json({"tipo": "autenticar", "token": token})
    assert ws.receive_json()["tipo"] == TipoEvento.CONECTADO


def esperar_cierre(ws: WebSocketTestSession) -> WebSocketDisconnect:
    with pytest.raises(WebSocketDisconnect) as cierre:
        ws.receive_json()
    return cierre.value


def marcador(usuario: Usuario) -> str:
    """Publica un evento de control: si es lo siguiente que llega, no llegó nada antes."""
    marca = str(uuid.uuid4())
    assert publicar(usuario.id, Evento("marcador", {"marca": marca}))
    return marca


def siguiente_es_marcador(ws: WebSocketTestSession, usuario: Usuario) -> None:
    marca = marcador(usuario)
    assert ws.receive_json()["datos"] == {"marca": marca}


def token_que_vence_en(usuario: Usuario, segundos: int) -> str:
    ahora = datetime.now(UTC)
    claims = {
        "sub": str(usuario.id),
        "rol": usuario.rol,
        "token_version": usuario.token_version,
        "iat": ahora,
        "exp": ahora + timedelta(seconds=segundos),
    }
    return jwt.encode(claims, settings.jwt_secret, algorithm="HS256")


def test_token_valido_recibe_conectado(cliente: TestClient, dos_gerentes: DosGerentes) -> None:
    with cliente.websocket_connect(RUTA) as ws:
        ws.send_json({"tipo": "autenticar", "token": crear_token(dos_gerentes.uno.gerente)})
        evento = ws.receive_json()
    assert evento["tipo"] == "conectado"
    assert set(evento) == {"id", "tipo", "emitido_en", "datos"}


@pytest.mark.parametrize(
    "mensaje",
    [
        "no es json",
        json.dumps(["autenticar"]),
        json.dumps({"tipo": "otro", "token": "x"}),
        json.dumps({"tipo": "autenticar"}),
        json.dumps({"tipo": "autenticar", "token": ""}),
        json.dumps({"tipo": "autenticar", "token": "token-alterado"}),
    ],
)
def test_primer_mensaje_invalido_cierra_sin_autenticar(cliente: TestClient, mensaje: str) -> None:
    with cliente.websocket_connect(RUTA) as ws:
        ws.send_text(mensaje)
        cierre = esperar_cierre(ws)
    assert (cierre.code, cierre.reason) == (CIERRE_NO_AUTENTICADO, "NO_AUTENTICADO")


def test_mensaje_binario_cierra_sin_autenticar(cliente: TestClient) -> None:
    with cliente.websocket_connect(RUTA) as ws:
        ws.send_bytes(b"\x00")
        cierre = esperar_cierre(ws)
    assert cierre.reason == "NO_AUTENTICADO"


def test_sin_autenticar_a_tiempo_se_cierra(
    cliente: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(tiempo_real, "PLAZO_AUTENTICACION_SEGUNDOS", 0.1)
    with cliente.websocket_connect(RUTA) as ws:
        cierre = esperar_cierre(ws)
    assert (cierre.code, cierre.reason) == (CIERRE_NO_AUTENTICADO, "NO_AUTENTICADO")


def test_token_vencido_no_conecta(cliente: TestClient, dos_gerentes: DosGerentes) -> None:
    with cliente.websocket_connect(RUTA) as ws:
        ws.send_json(
            {"tipo": "autenticar", "token": token_que_vence_en(dos_gerentes.uno.gerente, -5)}
        )
        cierre = esperar_cierre(ws)
    assert cierre.reason == "NO_AUTENTICADO"


def test_token_revocado_no_conecta(
    cliente: TestClient, db: Session, dos_gerentes: DosGerentes
) -> None:
    gerente = dos_gerentes.uno.gerente
    token = crear_token(gerente)
    gerente.token_version += 1
    db.flush()
    with cliente.websocket_connect(RUTA) as ws:
        ws.send_json({"tipo": "autenticar", "token": token})
        cierre = esperar_cierre(ws)
    assert (cierre.code, cierre.reason) == (CIERRE_NO_AUTENTICADO, "SESION_REVOCADA")


def test_cuenta_inactiva_no_conecta(
    cliente: TestClient, db: Session, dos_gerentes: DosGerentes
) -> None:
    asistente = dos_gerentes.uno.asistente
    asistente.estado = "inactiva"
    db.flush()
    with cliente.websocket_connect(RUTA) as ws:
        ws.send_json({"tipo": "autenticar", "token": crear_token(asistente)})
        cierre = esperar_cierre(ws)
    assert (cierre.code, cierre.reason) == (CIERRE_NO_AUTENTICADO, "CUENTA_INACTIVA")


def test_cada_usuario_recibe_solo_lo_suyo(
    cliente: TestClient,
    db: Session,
    dos_gerentes: DosGerentes,
    confirmar: Callable[[], None],
) -> None:
    uno, dos = dos_gerentes.uno, dos_gerentes.dos
    with (
        cliente.websocket_connect(RUTA) as gerente_uno,
        cliente.websocket_connect(RUTA) as asistente_uno,
        cliente.websocket_connect(RUTA) as gerente_dos,
        cliente.websocket_connect(RUTA) as asistente_dos,
    ):
        for ws, usuario in [
            (gerente_uno, uno.gerente),
            (asistente_uno, uno.asistente),
            (gerente_dos, dos.gerente),
            (asistente_dos, dos.asistente),
        ]:
            autenticar(ws, crear_token(usuario))

        notificar(db, uno.gerente, TipoNotificacion.COMENTARIO, "Comentario", "Hola")
        confirmar()

        evento = gerente_uno.receive_json()
        assert evento["tipo"] == "notificacion"
        assert evento["datos"]["titulo"] == "Comentario"
        siguiente_es_marcador(asistente_uno, uno.asistente)
        siguiente_es_marcador(gerente_dos, dos.gerente)
        siguiente_es_marcador(asistente_dos, dos.asistente)


def test_varias_conexiones_del_mismo_usuario_reciben_el_evento(
    cliente: TestClient, dos_gerentes: DosGerentes
) -> None:
    gerente = dos_gerentes.uno.gerente
    with (
        cliente.websocket_connect(RUTA) as celular,
        cliente.websocket_connect(RUTA) as computadora,
    ):
        autenticar(celular, crear_token(gerente))
        autenticar(computadora, crear_token(gerente))
        marca = marcador(gerente)
        assert celular.receive_json()["datos"] == {"marca": marca}
        assert computadora.receive_json()["datos"] == {"marca": marca}


def test_lo_que_envia_el_cliente_se_ignora(cliente: TestClient, dos_gerentes: DosGerentes) -> None:
    uno, dos = dos_gerentes.uno, dos_gerentes.dos
    with cliente.websocket_connect(RUTA) as ws:
        autenticar(ws, crear_token(uno.asistente))
        ws.send_json({"tipo": "suscribir", "usuario_id": str(dos.gerente.id)})
        ws.send_bytes(b"\x01")
        marcador(dos.gerente)
        siguiente_es_marcador(ws, uno.asistente)


def test_cierre_de_sesion_forzado_cierra_la_conexion(
    cliente: TestClient,
    db: Session,
    dos_gerentes: DosGerentes,
    confirmar: Callable[[], None],
) -> None:
    asistente = dos_gerentes.uno.asistente
    with cliente.websocket_connect(RUTA) as ws:
        autenticar(ws, crear_token(asistente))
        asistente.token_version += 1
        avisar_cierre_sesion(db, asistente.id)
        confirmar()
        evento = ws.receive_json()
        cierre = esperar_cierre(ws)
    assert evento["tipo"] == "sesion_cerrada"
    assert evento["datos"] == {"code": "SESION_REVOCADA"}
    assert (cierre.code, cierre.reason) == (CIERRE_NO_AUTENTICADO, "SESION_REVOCADA")


def test_el_aviso_de_cierre_no_afecta_a_la_sesion_renovada(
    cliente: TestClient,
    db: Session,
    dos_gerentes: DosGerentes,
    confirmar: Callable[[], None],
) -> None:
    gerente = dos_gerentes.uno.gerente
    gerente.token_version += 1
    db.flush()
    with cliente.websocket_connect(RUTA) as ws:
        autenticar(ws, crear_token(gerente))
        avisar_cierre_sesion(db, gerente.id)
        confirmar()
        siguiente_es_marcador(ws, gerente)


def test_revocacion_sin_aviso_se_detecta_al_entregar(
    cliente: TestClient, db: Session, dos_gerentes: DosGerentes
) -> None:
    gerente = dos_gerentes.uno.gerente
    with cliente.websocket_connect(RUTA) as ws:
        autenticar(ws, crear_token(gerente))
        # Se revoca sin publicar el aviso, como si Redis hubiera fallado en ese momento.
        gerente.token_version += 1
        db.flush()
        marcador(gerente)
        evento = ws.receive_json()
        cierre = esperar_cierre(ws)
    assert evento["datos"] == {"code": "SESION_REVOCADA"}
    assert cierre.reason == "SESION_REVOCADA"


def test_cuenta_desactivada_con_la_conexion_abierta_se_cierra(
    cliente: TestClient, db: Session, dos_gerentes: DosGerentes
) -> None:
    asistente = dos_gerentes.uno.asistente
    with cliente.websocket_connect(RUTA) as ws:
        autenticar(ws, crear_token(asistente))
        asistente.estado = "inactiva"
        db.flush()
        marcador(asistente)
        ws.receive_json()
        cierre = esperar_cierre(ws)
    assert cierre.reason == "CUENTA_INACTIVA"


def test_al_vencer_el_token_se_cierra_la_conexion(
    cliente: TestClient, dos_gerentes: DosGerentes
) -> None:
    with cliente.websocket_connect(RUTA) as ws:
        autenticar(ws, token_que_vence_en(dos_gerentes.uno.gerente, 2))
        evento = ws.receive_json()
        cierre = esperar_cierre(ws)
    assert evento["datos"] == {"code": "NO_AUTENTICADO"}
    assert (cierre.code, cierre.reason) == (CIERRE_NO_AUTENTICADO, "NO_AUTENTICADO")


def test_al_reconectar_lo_pendiente_sigue_en_la_base(
    cliente: TestClient,
    db: Session,
    dos_gerentes: DosGerentes,
    confirmar: Callable[[], None],
) -> None:
    gerente = dos_gerentes.uno.gerente
    with cliente.websocket_connect(RUTA) as ws:
        autenticar(ws, crear_token(gerente))
    # Desconectado: el evento no llega a nadie, pero la notificación queda guardada.
    creada = notificar(db, gerente, TipoNotificacion.DEUDA_CREADA, "Deuda creada", "Luz")
    confirmar()
    assert creada is not None
    with cliente.websocket_connect(RUTA) as ws:
        autenticar(ws, crear_token(gerente))
        siguiente_es_marcador(ws, gerente)
    pendientes = db.scalars(
        select(Notificacion.id).where(
            Notificacion.usuario_id == gerente.id, Notificacion.leida_en.is_(None)
        )
    ).all()
    assert pendientes == [creada.id]


class GestorQueAnota(GestorConexiones):
    def __init__(self) -> None:
        super().__init__()
        self.a_todos_recibidos: list[dict[str, Any]] = []
        self.despachados: list[str | bytes] = []

    async def a_todos(self, evento: dict[str, Any]) -> None:
        self.a_todos_recibidos.append(evento)

    async def despachar(self, mensaje: str | bytes) -> None:
        self.despachados.append(mensaje)


class RedisQueNoConecta:
    async def __aenter__(self) -> "RedisQueNoConecta":
        raise redis.ConnectionError("Redis no responde")

    async def __aexit__(self, *_: object) -> None:
        return None


def test_al_recuperar_redis_se_pide_resincronizar(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(conexiones, "ESPERA_INICIAL_SEGUNDOS", 0.01)
    intentos: list[int] = []

    def conectar() -> Any:
        intentos.append(1)
        if len(intentos) == 1:
            return RedisQueNoConecta()
        return redis.asyncio.Redis.from_url(settings.redis_url)

    async def probar() -> GestorQueAnota:
        gestor = GestorQueAnota()
        listo = asyncio.Event()
        tarea = asyncio.create_task(escuchar(gestor, listo, conectar))
        await asyncio.wait_for(listo.wait(), 5)
        await asyncio.sleep(0.05)
        await detener_suscriptor(tarea)
        return gestor

    gestor = asyncio.run(probar())
    assert len(intentos) == 2
    assert [e["tipo"] for e in gestor.a_todos_recibidos] == ["resincronizar"]


def test_el_suscriptor_reparte_lo_publicado(monkeypatch: pytest.MonkeyPatch) -> None:
    async def probar() -> GestorQueAnota:
        gestor = GestorQueAnota()
        tarea = await iniciar_suscriptor(gestor)
        usuario_id = uuid.uuid4()
        await asyncio.to_thread(publicar, usuario_id, Evento(TipoEvento.NOTIFICACION))
        for _ in range(100):
            if gestor.despachados:
                break
            await asyncio.sleep(0.02)
        await detener_suscriptor(tarea)
        return gestor

    gestor = asyncio.run(probar())
    assert len(gestor.despachados) == 1
    assert gestor.a_todos_recibidos == []


def test_si_redis_no_responde_al_arrancar_el_server_sigue(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setattr(conexiones, "ESPERA_SUSCRIPCION_SEGUNDOS", 0.2)
    monkeypatch.setattr(conexiones, "crear_cliente_async", lambda: RedisQueNoConecta())

    async def probar() -> bool:
        tarea = await iniciar_suscriptor(GestorQueAnota())
        sigue = not tarea.done()
        await detener_suscriptor(tarea)
        return sigue

    with caplog.at_level(logging.WARNING, logger="app.tiempo_real"):
        assert asyncio.run(probar()) is True
    assert "Redis no respondió al arrancar" in caplog.text


@pytest.mark.parametrize(
    "mensaje",
    [
        "no es json",
        json.dumps({"evento": {}}),
        json.dumps({"usuario_id": "no-es-uuid", "evento": {}}),
        json.dumps({"usuario_id": str(uuid.uuid4()), "evento": "texto"}),
    ],
)
def test_mensaje_del_canal_con_formato_invalido_se_descarta(
    mensaje: str, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.WARNING, logger="app.tiempo_real"):
        asyncio.run(GestorConexiones().despachar(mensaje))
    assert "formato inválido" in caplog.text


def test_entregar_a_un_usuario_sin_conexiones_no_hace_nada() -> None:
    gestor = GestorConexiones()
    inicio = time.monotonic()
    asyncio.run(gestor.entregar(uuid.uuid4(), Evento(TipoEvento.NOTIFICACION).a_json()))
    assert time.monotonic() - inicio < 1
    assert gestor.conexiones_de(uuid.uuid4()) == []


class ConexionQueFalla:
    usuario_id = uuid.UUID(int=1)

    async def entregar(self, _: dict[str, Any]) -> None:
        raise RuntimeError("La base no responde")


class ConexionQueAnota:
    usuario_id = uuid.UUID(int=1)

    def __init__(self) -> None:
        self.recibidos: list[dict[str, Any]] = []

    async def entregar(self, evento: dict[str, Any]) -> None:
        self.recibidos.append(evento)


def test_un_fallo_al_entregar_no_detiene_el_reparto(caplog: pytest.LogCaptureFixture) -> None:
    gestor = GestorConexiones()
    sana = ConexionQueAnota()
    gestor.agregar(ConexionQueFalla())  # type: ignore[arg-type]
    gestor.agregar(sana)  # type: ignore[arg-type]
    evento = Evento(TipoEvento.NOTIFICACION).a_json()
    with caplog.at_level(logging.ERROR, logger="app.tiempo_real"):
        asyncio.run(gestor.entregar(uuid.UUID(int=1), evento))
    assert sana.recibidos == [evento]
    assert "No se pudo entregar el evento" in caplog.text
