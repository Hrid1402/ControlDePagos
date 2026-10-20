"""Servicio común de notificaciones (H29): todas las historias notifican con notificar().

La notificación se inserta en la transacción de quien llama, como la auditoría: el commit lo hace
quien llama y el evento "notificacion" sale por WebSocket solo después de ese commit.
"""

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.dependencias import gerente_de
from app.core.eventos import Evento, TipoEvento, publicar_tras_commit
from app.core.tiempo import ahora_lima, zona_horaria
from app.models import Deuda, Notificacion, PreferenciaNotificacion, Usuario
from app.schemas.notificaciones import NotificacionSalida

# En Sprint 1 la app es el único canal; correo y WhatsApp llegan con T07.
CANAL_APP = "app"


class TipoNotificacion(StrEnum):
    """Tipos permitidos por ck_notificacion_tipo."""

    DEUDA_CREADA = "deuda_creada"
    DEUDA_PAGADA = "deuda_pagada"
    POR_VENCER = "por_vencer"
    VENCIDA = "vencida"
    COMPROBANTE_RECHAZADO = "comprobante_rechazado"
    COMPROBANTE_EN_REVISION = "comprobante_en_revision"
    APROBACION_PENDIENTE = "aprobacion_pendiente"
    ORDEN_URGENTE = "orden_urgente"
    NO_PUDE_PAGAR = "no_pude_pagar"
    RECORDATORIO_COMPROBANTE = "recordatorio_comprobante"
    COMENTARIO = "comentario"
    ROBOT_FALLA = "robot_falla"
    REEMBOLSO = "reembolso"


def en_silencio(usuario: Usuario, ahora: datetime) -> bool:
    """Si la hora de Lima cae en el horario silencioso del usuario. Admite rangos que cruzan la
    medianoche (22:00 a 07:00); sin alguno de los dos extremos, o con ambos iguales, no hay
    silencio."""
    desde, hasta = usuario.silencio_desde, usuario.silencio_hasta
    if desde is None or hasta is None or desde == hasta:
        return False
    hora = ahora.astimezone(zona_horaria()).time()
    if desde < hasta:
        return desde <= hora < hasta
    return hora >= desde or hora < hasta


def preferencia_activa(db: Session, usuario_id: uuid.UUID, tipo: TipoNotificacion) -> bool:
    """Preferencia del canal app; sin registro, el evento está activo."""
    activa = db.scalar(
        select(PreferenciaNotificacion.activa).where(
            PreferenciaNotificacion.usuario_id == usuario_id,
            PreferenciaNotificacion.tipo == tipo.value,
            PreferenciaNotificacion.canal == CANAL_APP,
        )
    )
    return activa is not False


def notificar(
    db: Session,
    usuario: Usuario,
    tipo: TipoNotificacion,
    titulo: str,
    mensaje: str,
    deuda_id: uuid.UUID | None = None,
    urgente: bool = False,
    *,
    clave_evento: str | None = None,
    ahora: datetime | None = None,
) -> Notificacion | None:
    """Guarda la notificación y encola su evento. Devuelve None si no se notifica: cuenta
    inactiva o eliminada, preferencia desactivada o clave_evento ya notificada.

    Las urgentes ignoran la preferencia y el horario silencioso: la app es el único canal y una
    orden urgente o una aprobación pendiente no pueden perderse. En silencio, las demás se
    guardan con aviso=false: el cliente las cuenta sin sonido ni aviso emergente.

    clave_evento identifica evento/destinatario/ciclo (por ejemplo "por_vencer:<deuda>:<fecha>")
    para que repetir un job o una acción no duplique el aviso.
    """
    if usuario.eliminado_en is not None or usuario.estado != "activa":
        return None
    if deuda_id is not None:
        deuda = db.get(Deuda, deuda_id)
        if deuda is None or deuda.gerente_id != gerente_de(usuario):
            raise ValueError("La deuda no pertenece al gerente del destinatario.")
    if not urgente and not preferencia_activa(db, usuario.id, tipo):
        return None

    notificacion = db.scalar(
        insert(Notificacion)
        .values(
            usuario_id=usuario.id,
            tipo=tipo.value,
            titulo=titulo,
            mensaje=mensaje,
            deuda_id=deuda_id,
            urgente=urgente,
            clave_evento=clave_evento,
        )
        .on_conflict_do_nothing(constraint="uq_notificacion_usuario_id_clave_evento")
        .returning(Notificacion)
    )
    if notificacion is None:
        return None

    aviso = urgente or not en_silencio(usuario, ahora or ahora_lima())
    datos = NotificacionSalida.model_validate(notificacion).model_dump(mode="json")
    publicar_tras_commit(db, usuario.id, Evento(TipoEvento.NOTIFICACION, {**datos, "aviso": aviso}))
    return notificacion
