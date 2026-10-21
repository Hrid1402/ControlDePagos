"""Comentarios de una deuda entre el gerente y su asistente (H17 CA06, TASK-54).

Comentan las dos cuentas del gerente sobre sus deudas; la de otro gerente responde el mismo 404
que una inexistente. El texto va de 1 a 500 caracteres. Una deuda anulada es de solo lectura: se
leen sus comentarios pero no se agregan (409).

Al comentar se avisa al otro rol con el servicio común de notificaciones: el comentario del
gerente a su asistente activa y el de la asistente a su gerente. La notificación y su evento salen
después del commit, como en el resto de la aplicación.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.dependencias import gerente_de
from app.core.errores import ErrorApi
from app.models import Comentario, Deuda, Servicio, Usuario
from app.services.auditoria import nombre_de
from app.services.notificaciones import TipoNotificacion, notificar

LARGO_AVISO = 120


@dataclass(frozen=True)
class FilaComentario:
    comentario: Comentario
    autor: Usuario


def deuda_visible(db: Session, usuario: Usuario, deuda_id: uuid.UUID) -> Deuda:
    deuda = db.scalar(
        select(Deuda).where(Deuda.id == deuda_id, Deuda.gerente_id == gerente_de(usuario))
    )
    if deuda is None:
        raise ErrorApi(404, "NO_ENCONTRADO", "No se encontró la deuda.")
    return deuda


def listar_comentarios(db: Session, usuario: Usuario, deuda_id: uuid.UUID) -> list[FilaComentario]:
    """Del más antiguo al más reciente, como una conversación."""
    deuda = deuda_visible(db, usuario, deuda_id)
    filas = db.execute(
        select(Comentario, Usuario)
        .join(Usuario, Usuario.id == Comentario.usuario_id)
        .where(Comentario.deuda_id == deuda.id)
        .order_by(Comentario.creado_en, Comentario.id)
    )
    return [FilaComentario(c, u) for c, u in filas]


def destinatario(db: Session, usuario: Usuario, deuda: Deuda) -> Usuario | None:
    """El otro rol: si comenta la asistente, el gerente; si comenta el gerente, su asistente
    activa."""
    if usuario.rol == "asistente":
        return db.get(Usuario, deuda.gerente_id)
    return db.scalar(
        select(Usuario).where(
            Usuario.gerente_id == deuda.gerente_id,
            Usuario.rol == "asistente",
            Usuario.estado == "activa",
            Usuario.eliminado_en.is_(None),
        )
    )


def comentar(
    db: Session,
    usuario: Usuario,
    deuda_id: uuid.UUID,
    texto: str,
    ahora: datetime | None = None,
) -> FilaComentario:
    deuda = deuda_visible(db, usuario, deuda_id)
    if deuda.estado == "anulada":
        raise ErrorApi(
            409, "ESTADO_NO_PERMITIDO", "La deuda está anulada: ya no admite comentarios."
        )
    texto = texto.strip()
    comentario = Comentario(deuda_id=deuda.id, usuario_id=usuario.id, texto=texto)
    db.add(comentario)
    db.flush()
    otro = destinatario(db, usuario, deuda)
    if otro is not None:
        servicio = db.get(Servicio, deuda.servicio_id)
        nombre = (servicio.alias or servicio.empresa_nombre) if servicio else None
        resumen = texto if len(texto) <= LARGO_AVISO else f"{texto[: LARGO_AVISO - 1]}…"
        notificar(
            db,
            otro,
            TipoNotificacion.COMENTARIO,
            f"Comentario en {nombre}" if nombre else "Nuevo comentario",
            f"{nombre_de(usuario)}: {resumen}",
            deuda_id=deuda.id,
            clave_evento=f"comentario:{comentario.id}",
            ahora=ahora,
        )
    return FilaComentario(comentario, usuario)
