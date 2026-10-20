"""Historial compartido: la contraseña actual vive en usuario y las anteriores en historial.

Las lecturas toleran hashes repetidos o el hash vigente que dejaron los flujos anteriores,
sin borrar registros ni reducir la ventana de las tres contraseñas anteriores.
El llamador debe bloquear al usuario hasta confirmar su transacción, y antes que sus tokens de
recuperación.
"""

from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.seguridad import hashear_contrasena, verificar_contrasena
from app.models import HistorialContrasena, TokenRestablecimiento, Usuario

CONTRASENAS_ANTERIORES = 3


def es_reutilizada(db: Session, usuario: Usuario, nueva: str) -> bool:
    if verificar_contrasena(nueva, usuario.password_hash):
        return True

    anteriores = db.scalars(
        select(HistorialContrasena.password_hash)
        .where(
            HistorialContrasena.usuario_id == usuario.id,
            HistorialContrasena.password_hash != usuario.password_hash,
        )
        .order_by(HistorialContrasena.creado_en.desc(), HistorialContrasena.id.desc())
    )
    revisados: set[str] = set()
    for password_hash in anteriores:
        if password_hash in revisados:
            continue
        revisados.add(password_hash)
        if verificar_contrasena(nueva, password_hash):
            return True
        if len(revisados) == CONTRASENAS_ANTERIORES:
            break
    return False


def actualizar_contrasena(db: Session, usuario: Usuario, nueva: str) -> None:
    """Guarda la nueva contraseña, revoca las sesiones y deja usados los enlaces de recuperación
    pendientes: uno pedido antes del cambio ya no sirve para cambiarla otra vez."""
    db.add(HistorialContrasena(usuario_id=usuario.id, password_hash=usuario.password_hash))
    usuario.password_hash = hashear_contrasena(nueva)
    usuario.contrasena_inicial = False
    usuario.token_version += 1
    db.execute(
        update(TokenRestablecimiento)
        .where(
            TokenRestablecimiento.usuario_id == usuario.id,
            TokenRestablecimiento.usado_en.is_(None),
        )
        .values(usado_en=datetime.now(UTC))
    )
