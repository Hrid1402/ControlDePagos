"""Ingreso al sistema (H01): credenciales, bloqueo por intentos y estado de cuenta.

Un intento fallido de una cuenta conocida se confirma con commit antes de lanzar el error: si no,
la sesión se cierra sin confirmar y se pierden el contador, el bloqueo y el evento de auditoría.
"""

import math
from datetime import UTC, datetime, timedelta
from enum import StrEnum

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.dependencias import Origen
from app.core.errores import ErrorApi
from app.core.seguridad import HASH_RELLENO, verificar_contrasena
from app.models import Usuario
from app.services.auditoria import Accion, registrar_auditoria, registrar_login_desconocido

MAXIMO_INTENTOS = 5
MINUTOS_BLOQUEO = 15


class Motivo(StrEnum):
    """Motivo de un login_fallido, guardado en el detalle de la auditoría."""

    CONTRASENA_INCORRECTA = "contrasena_incorrecta"
    CUENTA_BLOQUEADA = "cuenta_bloqueada"
    CUENTA_INACTIVA = "cuenta_inactiva"
    CUENTA_ELIMINADA = "cuenta_eliminada"


def credenciales_invalidas() -> ErrorApi:
    """Respuesta única para usuario inexistente, cuenta eliminada o contraseña incorrecta: no
    revela cuál de los dos campos falló."""
    return ErrorApi(401, "CREDENCIALES_INVALIDAS", "Usuario o contraseña incorrectos.")


def cuenta_bloqueada(bloqueado_hasta: datetime, ahora: datetime) -> ErrorApi:
    minutos = max(1, math.ceil((bloqueado_hasta - ahora).total_seconds() / 60))
    unidad = "minuto" if minutos == 1 else "minutos"
    return ErrorApi(
        423,
        "CUENTA_BLOQUEADA",
        f"Tu cuenta está bloqueada por intentos fallidos. Intenta de nuevo en {minutos} {unidad}.",
    )


def cuenta_inactiva() -> ErrorApi:
    return ErrorApi(403, "CUENTA_INACTIVA", "Cuenta inactiva, contacta al gerente.")


def buscar_para_ingreso(db: Session, username: str) -> Usuario | None:
    """Cuenta del username sin distinguir mayúsculas, bloqueada con FOR UPDATE hasta el commit
    para que dos intentos simultáneos no lean el mismo contador. uq_usuario_username no es parcial
    y admite una sola fila; si llegara a haber varias, primero va la no eliminada."""
    return db.scalar(
        select(Usuario)
        .where(func.lower(Usuario.username) == func.lower(username))
        .order_by(Usuario.eliminado_en.is_not(None))
        .limit(1)
        .with_for_update()
    )


def rechazar(
    db: Session, usuario: Usuario, motivo: Motivo, error: ErrorApi, origen: Origen
) -> ErrorApi:
    """Audita el intento fallido y lo confirma junto con el contador; devuelve el error a lanzar."""
    detalle = {
        "motivo": motivo.value,
        "intentos_fallidos": usuario.intentos_fallidos,
        "bloqueado_hasta": usuario.bloqueado_hasta,
    }
    registrar_auditoria(
        db, usuario, Accion.LOGIN_FALLIDO, "usuario", usuario.id, detalle, origen=origen
    )
    db.commit()
    return error


def iniciar_sesion(db: Session, username: str, contrasena: str, origen: Origen) -> Usuario:
    """Valida las credenciales y devuelve el usuario que ingresa. Tras 5 contraseñas incorrectas
    la cuenta se bloquea 15 minutos; el contador se reinicia al ingresar o al terminar el
    bloqueo. El estado inactivo solo se revela a quien conoce la contraseña."""
    usuario = buscar_para_ingreso(db, username)
    if usuario is None:
        # Verificar igual iguala el tiempo de respuesta al de una cuenta real.
        verificar_contrasena(contrasena, HASH_RELLENO)
        registrar_login_desconocido(origen)
        raise credenciales_invalidas()

    ahora = datetime.now(UTC)
    if usuario.eliminado_en is not None:
        verificar_contrasena(contrasena, usuario.password_hash)
        raise rechazar(db, usuario, Motivo.CUENTA_ELIMINADA, credenciales_invalidas(), origen)

    if usuario.bloqueado_hasta is not None:
        if usuario.bloqueado_hasta > ahora:
            error = cuenta_bloqueada(usuario.bloqueado_hasta, ahora)
            raise rechazar(db, usuario, Motivo.CUENTA_BLOQUEADA, error, origen)
        # Terminó el bloqueo: el contador vuelve a empezar.
        usuario.intentos_fallidos = 0
        usuario.bloqueado_hasta = None

    if not verificar_contrasena(contrasena, usuario.password_hash):
        usuario.intentos_fallidos += 1
        error = credenciales_invalidas()
        if usuario.intentos_fallidos >= MAXIMO_INTENTOS:
            usuario.bloqueado_hasta = ahora + timedelta(minutes=MINUTOS_BLOQUEO)
            error = cuenta_bloqueada(usuario.bloqueado_hasta, ahora)
        raise rechazar(db, usuario, Motivo.CONTRASENA_INCORRECTA, error, origen)

    if usuario.estado != "activa":
        raise rechazar(db, usuario, Motivo.CUENTA_INACTIVA, cuenta_inactiva(), origen)

    usuario.intentos_fallidos = 0
    usuario.bloqueado_hasta = None
    usuario.ultimo_ingreso = ahora
    registrar_auditoria(db, usuario, Accion.LOGIN_EXITOSO, "usuario", usuario.id, origen=origen)
    db.commit()
    return usuario
