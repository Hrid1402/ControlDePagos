"""Historial compartido: la contraseña actual vive en usuario y las anteriores en historial.

Las lecturas toleran hashes repetidos o el hash vigente que dejaron los flujos anteriores,
sin borrar registros ni reducir la ventana de las tres contraseñas anteriores.
El llamador debe bloquear al usuario hasta confirmar su transacción.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.seguridad import hashear_contrasena, verificar_contrasena
from app.models import HistorialContrasena, Usuario

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
    db.add(HistorialContrasena(usuario_id=usuario.id, password_hash=usuario.password_hash))
    usuario.password_hash = hashear_contrasena(nueva)
    usuario.contrasena_inicial = False
    usuario.token_version += 1
