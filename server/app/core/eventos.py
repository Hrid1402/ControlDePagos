"""Eventos en tiempo real que salen después del commit.

Quien cambia datos encola el evento con publicar_tras_commit en su misma sesión. Al confirmar la
transacción se publica en Redis, y cada proceso del server lo entrega a las conexiones WebSocket
de su destinatario (app/core/conexiones.py). Si la transacción se deshace, el evento se descarta.

Publicar es el último paso y no puede deshacer lo ya confirmado: si Redis falla, se registra en
el log y el cliente recupera el estado por la API al reconectar o al recibir resincronizar.

El mismo mecanismo ejecuta otras acciones tras el commit con ejecutar_tras_commit; así encola las
tareas de Celery app/workers/encolar.py. Eventos y acciones salen en el orden en que se encolaron.
"""

import json
import logging
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from functools import cache
from typing import Any

import redis
from sqlalchemy import event
from sqlalchemy.orm import Session, SessionTransaction

from app.core.config import settings
from app.core.tiempo import ahora_lima

logger = logging.getLogger("app.tiempo_real")

CANAL = "control_pagos:eventos"
ESPERA_REDIS_SEGUNDOS = 2

# Claves en Session.info: acciones encoladas (publicar un evento, encolar una tarea) y, por cada
# savepoint abierto, cuántas había al abrirlo, para descartar solo las del savepoint si este se
# deshace.
PENDIENTES = "eventos_pendientes"
MARCAS = "eventos_marcas"

Accion = Callable[[], object]


class TipoEvento(StrEnum):
    """Tipos de evento del canal. Cada historia agrega aquí los suyos (órdenes, comprobantes)."""

    CONECTADO = "conectado"
    NOTIFICACION = "notificacion"
    SESION_CERRADA = "sesion_cerrada"
    RESINCRONIZAR = "resincronizar"
    PAGO_CANCELADO = "pago_cancelado"
    # Órdenes urgentes: solo se publican con publicar_evento_orden (app/services/ordenes.py).
    ORDEN_NUEVA = "orden_nueva"
    ORDEN_VISTA = "orden_vista"
    ORDEN_ACEPTADA = "orden_aceptada"
    ORDEN_RECHAZADA = "orden_rechazada"
    ORDEN_CANCELADA = "orden_cancelada"
    # Resultado de la validación de un comprobante (app/services/validacion.py).
    COMPROBANTE_RESULTADO = "comprobante_resultado"


@dataclass(frozen=True)
class Evento:
    """Mensaje que recibe el cliente. datos debe contener solo valores JSON; el id permite al
    cliente descartar un evento repetido."""

    tipo: str
    datos: dict[str, Any] = field(default_factory=dict)
    id: uuid.UUID = field(default_factory=uuid.uuid4)
    emitido_en: datetime = field(default_factory=ahora_lima)

    def a_json(self) -> dict[str, Any]:
        return {
            "id": str(self.id),
            "tipo": self.tipo,
            "emitido_en": self.emitido_en.isoformat(),
            "datos": self.datos,
        }


@cache
def cliente_redis() -> redis.Redis:
    return redis.Redis.from_url(
        settings.redis_url,
        socket_timeout=ESPERA_REDIS_SEGUNDOS,
        socket_connect_timeout=ESPERA_REDIS_SEGUNDOS,
    )


def ejecutar_tras_commit(db: Session, accion: Accion) -> None:
    """Ejecuta accion solo si la transacción de db se confirma. La acción no puede deshacer lo
    confirmado: debe atrapar y registrar sus propios fallos; si aun así lanza, se registra en el
    log y siguen las demás."""
    db.info.setdefault(PENDIENTES, []).append(accion)


def publicar_tras_commit(db: Session, usuario_id: uuid.UUID, evento: Evento) -> None:
    """Encola un evento para un usuario; sale solo si la transacción de db se confirma."""
    ejecutar_tras_commit(db, lambda: publicar(usuario_id, evento))


def avisar_cierre_sesion(db: Session, usuario_id: uuid.UUID) -> None:
    """Tras revocar las sesiones (token_version + 1), cierra los WebSocket con token anterior."""
    publicar_tras_commit(db, usuario_id, Evento(TipoEvento.SESION_CERRADA))


def publicar(usuario_id: uuid.UUID, evento: Evento) -> bool:
    """Publica en Redis para todos los procesos. Devuelve False si no se pudo."""
    mensaje = json.dumps({"usuario_id": str(usuario_id), "evento": evento.a_json()})
    try:
        cliente_redis().publish(CANAL, mensaje)
    except redis.RedisError:
        logger.warning(
            "No se pudo publicar el evento %s (tipo=%s, usuario=%s)",
            evento.id,
            evento.tipo,
            usuario_id,
            exc_info=True,
        )
        return False
    return True


@event.listens_for(Session, "after_transaction_create")
def marcar_savepoint(sesion: Session, transaccion: SessionTransaction) -> None:
    if transaccion.nested:
        sesion.info.setdefault(MARCAS, {})[transaccion] = len(sesion.info.get(PENDIENTES, []))


@event.listens_for(Session, "after_commit")
def enviar_pendientes(sesion: Session) -> None:
    # SQLAlchemy también avisa al liberar un savepoint; los eventos esperan al commit raíz.
    if sesion.in_nested_transaction():
        return
    for accion in sesion.info.pop(PENDIENTES, []):
        try:
            accion()
        except Exception:
            logger.exception("Falló una acción posterior al commit")


@event.listens_for(Session, "after_soft_rollback")
def descartar_pendientes(sesion: Session, anterior: SessionTransaction) -> None:
    if not anterior.nested:
        sesion.info.pop(PENDIENTES, None)
        return
    marca = sesion.info.get(MARCAS, {}).pop(anterior, None)
    if marca is not None:
        del sesion.info.get(PENDIENTES, [])[marca:]


@event.listens_for(Session, "after_transaction_end")
def limpiar_al_terminar(sesion: Session, transaccion: SessionTransaction) -> None:
    # Fin de la transacción raíz: tras el commit ya no queda nada; sin commit (por ejemplo, al
    # cerrar la sesión) se descarta. Las marcas de savepoint se usan después, en el rollback.
    if transaccion.parent is None and not transaccion.nested:
        sesion.info.pop(PENDIENTES, None)
        sesion.info.pop(MARCAS, None)
