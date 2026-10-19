"""Canal WebSocket compartido: notificaciones, órdenes, comprobantes y cierre de sesión.

Protocolo:
1. El cliente abre /api/v1/ws y, dentro de 10 segundos, envía
   {"tipo": "autenticar", "token": "<jwt>"}. El token no viaja en la URL para que no quede en
   los registros de acceso.
2. Si es válido recibe {"tipo": "conectado"}; si no, el server cierra con 4401 y la razón
   NO_AUTENTICADO, SESION_REVOCADA o CUENTA_INACTIVA.
3. Al recibir conectado o resincronizar, el cliente vuelve a pedir por la API lo pendiente:
   el canal solo avisa, los datos siempre están en la base.
"""

import asyncio
import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi.concurrency import run_in_threadpool

from app.core.conexiones import CIERRE_NO_AUTENTICADO, Conexion, gestor, validar_token
from app.core.dependencias import FabricaSesiones
from app.core.errores import ErrorApi
from app.core.eventos import Evento, TipoEvento

router = APIRouter(tags=["tiempo real"])

PLAZO_AUTENTICACION_SEGUNDOS = 10.0


async def leer_token_inicial(websocket: WebSocket) -> str | None:
    """Token del primer mensaje; None si no llega a tiempo o no tiene el formato esperado."""
    try:
        texto = await asyncio.wait_for(websocket.receive_text(), PLAZO_AUTENTICACION_SEGUNDOS)
        mensaje = json.loads(texto)
    except (TimeoutError, ValueError, KeyError):
        # KeyError: un mensaje binario no trae "text".
        return None
    if not isinstance(mensaje, dict) or mensaje.get("tipo") != "autenticar":
        return None
    token = mensaje.get("token")
    return token if isinstance(token, str) and token else None


@router.websocket("/ws")
async def tiempo_real(websocket: WebSocket, fabrica: FabricaSesiones) -> None:
    await websocket.accept()
    try:
        token = await leer_token_inicial(websocket)
    except WebSocketDisconnect:
        return
    if token is None:
        await websocket.close(CIERRE_NO_AUTENTICADO, "NO_AUTENTICADO")
        return
    try:
        usuario_id, expira_en = await run_in_threadpool(validar_token, fabrica, token)
    except ErrorApi as error:
        await websocket.close(CIERRE_NO_AUTENTICADO, error.code)
        return

    conexion = Conexion(websocket, usuario_id, token, expira_en, fabrica)
    gestor.agregar(conexion)
    try:
        await conexion.enviar(Evento(TipoEvento.CONECTADO).a_json())
        await conexion.atender()
    finally:
        gestor.quitar(conexion)
