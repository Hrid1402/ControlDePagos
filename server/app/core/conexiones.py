"""Conexiones WebSocket de este proceso y reparto de los eventos que llegan por Redis.

Cada proceso del server se suscribe al canal de eventos y entrega cada uno solo a las conexiones
autenticadas como su destinatario. Antes de cada entrega se vuelve a validar la sesión: una
conexión revocada, de una cuenta inactiva o con el token vencido se cierra aunque se haya perdido
el aviso de cierre.
"""

import asyncio
import json
import logging
import uuid
from collections.abc import Callable
from contextlib import AbstractContextManager, suppress
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import redis
import redis.asyncio
from fastapi import WebSocket, WebSocketDisconnect
from fastapi.concurrency import run_in_threadpool
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.dependencias import usuario_desde_token
from app.core.errores import ErrorApi
from app.core.eventos import CANAL, Evento, TipoEvento
from app.core.seguridad import leer_token

logger = logging.getLogger("app.tiempo_real")

# Código de cierre propio (4000-4999) para toda sesión no válida; la razón lleva el código de
# error de la API: NO_AUTENTICADO, SESION_REVOCADA o CUENTA_INACTIVA.
CIERRE_NO_AUTENTICADO = 4401
ESPERA_INICIAL_SEGUNDOS = 1.0
ESPERA_MAXIMA_SEGUNDOS = 30.0
ESPERA_SUSCRIPCION_SEGUNDOS = 2.0

Fabrica = Callable[[], AbstractContextManager[Session]]


def validar_token(fabrica: Fabrica, token: str) -> tuple[uuid.UUID, datetime]:
    """Usuario y vencimiento del token; lanza ErrorApi 401 con su código si no es válido."""
    claims = leer_token(token)
    with fabrica() as db:
        usuario = usuario_desde_token(db, token)
    return usuario.id, claims.expira_en


def motivo_invalido(fabrica: Fabrica, token: str) -> str | None:
    try:
        validar_token(fabrica, token)
    except ErrorApi as error:
        return error.code
    return None


@dataclass(eq=False)
class Conexion:
    websocket: WebSocket
    usuario_id: uuid.UUID
    token: str
    expira_en: datetime
    fabrica: Fabrica
    cerrada: asyncio.Event = field(default_factory=asyncio.Event)

    async def enviar(self, evento: dict[str, Any]) -> None:
        try:
            await self.websocket.send_json(evento)
        except (WebSocketDisconnect, RuntimeError, OSError):
            # El cliente ya se fue; el bucle de atender termina y la quita del gestor.
            self.cerrada.set()

    async def cerrar(self, motivo: str) -> None:
        if self.cerrada.is_set():
            return
        self.cerrada.set()
        with suppress(WebSocketDisconnect, RuntimeError, OSError):
            await self.websocket.send_json(
                Evento(TipoEvento.SESION_CERRADA, {"code": motivo}).a_json()
            )
            await self.websocket.close(CIERRE_NO_AUTENTICADO, motivo)

    async def entregar(self, evento: dict[str, Any]) -> None:
        if self.cerrada.is_set():
            return
        motivo = await run_in_threadpool(motivo_invalido, self.fabrica, self.token)
        if motivo is not None:
            await self.cerrar(motivo)
        elif evento.get("tipo") != TipoEvento.SESION_CERRADA:
            # Un aviso de cierre a una conexión todavía válida (con el token ya renovado) se omite.
            await self.enviar(evento)

    async def atender(self) -> None:
        """Mantiene la conexión hasta que el cliente se va, se cierra o vence el token. Lo que
        envía el cliente después de autenticarse se ignora: no puede pedir datos ni suscribirse."""
        recibir = asyncio.ensure_future(self.websocket.receive())
        cerrada = asyncio.ensure_future(self.cerrada.wait())
        try:
            while True:
                restante = (self.expira_en - datetime.now(UTC)).total_seconds()
                if restante <= 0:
                    await self.cerrar("NO_AUTENTICADO")
                    return
                hechas, _ = await asyncio.wait(
                    {recibir, cerrada}, timeout=restante, return_when=asyncio.FIRST_COMPLETED
                )
                if cerrada in hechas:
                    return
                if recibir in hechas:
                    try:
                        mensaje = recibir.result()
                    except (WebSocketDisconnect, RuntimeError):
                        return
                    if mensaje["type"] == "websocket.disconnect":
                        return
                    recibir = asyncio.ensure_future(self.websocket.receive())
        finally:
            recibir.cancel()
            cerrada.cancel()


class GestorConexiones:
    """Conexiones abiertas en este proceso, agrupadas por usuario."""

    def __init__(self) -> None:
        self._por_usuario: dict[uuid.UUID, set[Conexion]] = {}

    def agregar(self, conexion: Conexion) -> None:
        self._por_usuario.setdefault(conexion.usuario_id, set()).add(conexion)

    def quitar(self, conexion: Conexion) -> None:
        conexiones = self._por_usuario.get(conexion.usuario_id)
        if conexiones is None:
            return
        conexiones.discard(conexion)
        if not conexiones:
            del self._por_usuario[conexion.usuario_id]

    def conexiones_de(self, usuario_id: uuid.UUID) -> list[Conexion]:
        return list(self._por_usuario.get(usuario_id, ()))

    async def entregar(self, usuario_id: uuid.UUID, evento: dict[str, Any]) -> None:
        for conexion in self.conexiones_de(usuario_id):
            try:
                await conexion.entregar(evento)
            except Exception:
                # Un fallo con una conexión (por ejemplo, la base no responde al revalidar) no
                # detiene el reparto a las demás ni el suscriptor.
                logger.exception("No se pudo entregar el evento %s", evento.get("id"))

    async def a_todos(self, evento: dict[str, Any]) -> None:
        for usuario_id in list(self._por_usuario):
            await self.entregar(usuario_id, evento)

    async def despachar(self, mensaje: str | bytes) -> None:
        """Entrega un mensaje del canal: {"usuario_id": ..., "evento": {...}}."""
        try:
            datos = json.loads(mensaje)
            usuario_id = uuid.UUID(datos["usuario_id"])
            evento = datos["evento"]
            if not isinstance(evento, dict):
                raise TypeError("El evento debe ser un objeto.")
        except (ValueError, KeyError, TypeError):
            logger.warning("Se descartó un mensaje de tiempo real con formato inválido")
            return
        await self.entregar(usuario_id, evento)


gestor = GestorConexiones()


def crear_cliente_async() -> redis.asyncio.Redis:
    return redis.asyncio.Redis.from_url(settings.redis_url)


async def escuchar(
    gestor_: GestorConexiones,
    listo: asyncio.Event,
    conectar: Callable[[], redis.asyncio.Redis] | None = None,
) -> None:
    """Reparte los eventos del canal. Si se pierde Redis reintenta con espera creciente y, al
    volver, pide a todas las conexiones resincronizar por la API lo que pudo perderse."""
    conectar = conectar or crear_cliente_async
    espera = ESPERA_INICIAL_SEGUNDOS
    perdida = False
    while True:
        try:
            async with conectar() as cliente, cliente.pubsub() as suscripcion:
                await suscripcion.subscribe(CANAL)
                listo.set()
                espera = ESPERA_INICIAL_SEGUNDOS
                if perdida:
                    perdida = False
                    await gestor_.a_todos(Evento(TipoEvento.RESINCRONIZAR).a_json())
                async for mensaje in suscripcion.listen():
                    if mensaje["type"] == "message":
                        await gestor_.despachar(mensaje["data"])
        except (redis.RedisError, OSError):
            logger.warning(
                "Se perdió la conexión con Redis; se reintentará en %s s", espera, exc_info=True
            )
            perdida = True
            await asyncio.sleep(espera)
            espera = min(espera * 2, ESPERA_MAXIMA_SEGUNDOS)


async def iniciar_suscriptor(gestor_: GestorConexiones = gestor) -> asyncio.Task[None]:
    """Arranca el suscriptor y espera a que se suscriba. Si Redis no responde, el server arranca
    igual y el suscriptor sigue reintentando."""
    listo = asyncio.Event()
    tarea = asyncio.create_task(escuchar(gestor_, listo))
    try:
        await asyncio.wait_for(listo.wait(), ESPERA_SUSCRIPCION_SEGUNDOS)
    except TimeoutError:
        logger.warning("Redis no respondió al arrancar; el tiempo real se activará al reconectar")
    return tarea


async def detener_suscriptor(tarea: asyncio.Task[None]) -> None:
    tarea.cancel()
    with suppress(asyncio.CancelledError):
        await tarea
