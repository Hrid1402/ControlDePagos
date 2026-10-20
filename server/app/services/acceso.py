"""Ingreso al sistema (H01): credenciales, bloqueo por intentos y estado de cuenta.

Un intento fallido de una cuenta conocida se confirma con commit antes de lanzar el error: si no,
la sesión se cierra sin confirmar y se pierden el contador, el bloqueo y el evento de auditoría.
"""

import hashlib
import math
import secrets
from datetime import UTC, datetime, timedelta
from enum import StrEnum

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.dependencias import Origen, gerente_de
from app.core.email import enviar_correo
from app.core.errores import ErrorApi
from app.core.seguridad import HASH_RELLENO, hashear_contrasena, verificar_contrasena
from app.models import HistorialContrasena, TokenRestablecimiento, Usuario
from app.services.auditoria import Accion, registrar_auditoria, registrar_login_desconocido


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
    """Valida las credenciales y devuelve el usuario que ingresa. Tras intentos fallidos
    la cuenta se bloquea los minutos configurados; el contador se reinicia al ingresar o al
    terminar el bloqueo. El estado inactivo solo se revela a quien conoce la contraseña."""
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
        if usuario.intentos_fallidos >= settings.login_intentos_maximos:
            usuario.bloqueado_hasta = ahora + timedelta(minutes=settings.login_minutos_bloqueo)
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


MENSAJE_RECUPERACION_GENERICO = (
    "Si el correo está registrado, enviamos las instrucciones para restablecer tu contraseña."
)


def solicitar_recuperacion(db: Session, correo: str, origen: Origen) -> str:
    """Genera un token de un solo uso para restablecer contraseña y lo envía por correo.
    Siempre devuelve un mensaje genérico para evitar enumeración de cuentas."""
    usuario = db.scalar(
        select(Usuario).where(func.lower(Usuario.correo) == func.lower(correo)).limit(1)
    )

    if usuario is not None and usuario.eliminado_en is None and usuario.estado == "activa":
        token_crudo = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(token_crudo.encode()).hexdigest()
        expira_en = datetime.now(UTC) + timedelta(hours=1)

        registro = TokenRestablecimiento(
            usuario_id=usuario.id,
            token_hash=token_hash,
            expira_en=expira_en,
        )
        db.add(registro)
        db.commit()

        nombre = usuario.nombres or usuario.username
        cuerpo = (
            f"Hola {nombre},\n\n"
            f"Recibimos una solicitud para restablecer tu contraseña.\n"
            f"Tu código de restablecimiento es:\n\n{token_crudo}\n\n"
            f"Este código es válido por 1 hora.\n"
            f"Si no solicitaste este cambio, puedes ignorar este mensaje.\n"
        )
        enviar_correo(usuario.correo or correo, "Restablecimiento de contraseña", cuerpo)

    return MENSAJE_RECUPERACION_GENERICO


def restablecer_contrasena(
    db: Session, token_crudo: str, nueva_contrasena: str, origen: Origen
) -> str:
    """Valida el token de restablecimiento, actualiza la contraseña y revoca sesiones previas."""
    token_hash = hashlib.sha256(token_crudo.encode()).hexdigest()
    ahora = datetime.now(UTC)

    registro = db.scalar(
        select(TokenRestablecimiento)
        .where(TokenRestablecimiento.token_hash == token_hash)
        .limit(1)
        .with_for_update()
    )

    if registro is None or registro.usado_en is not None or registro.expira_en < ahora:
        raise ErrorApi(400, "TOKEN_INVALIDO", "El token de restablecimiento es inválido o expiró.")

    usuario = db.get(Usuario, registro.usuario_id)
    if usuario is None or usuario.eliminado_en is not None or usuario.estado != "activa":
        raise ErrorApi(400, "TOKEN_INVALIDO", "El token de restablecimiento es inválido o expiró.")

    # No se pueden reutilizar la contraseña actual ni las últimas del historial (hasta 3)
    ultimos_hashes = list(
        db.scalars(
            select(HistorialContrasena.password_hash)
            .where(HistorialContrasena.usuario_id == usuario.id)
            .order_by(HistorialContrasena.creado_en.desc(), HistorialContrasena.id.desc())
            .limit(3)
        )
    )

    hashes_a_revisar = [usuario.password_hash] + [
        h for h in ultimos_hashes if h != usuario.password_hash
    ]
    if any(verificar_contrasena(nueva_contrasena, h) for h in hashes_a_revisar[:3]):
        raise ErrorApi(
            400,
            "CONTRASENA_REPETIDA",
            "No puedes reutilizar ninguna de tus últimas 3 contraseñas.",
        )

    registro.usado_en = ahora
    usuario.password_hash = hashear_contrasena(nueva_contrasena)
    usuario.token_version += 1
    usuario.intentos_fallidos = 0
    usuario.bloqueado_hasta = None
    usuario.contrasena_inicial = False

    historial = HistorialContrasena(usuario_id=usuario.id, password_hash=usuario.password_hash)
    db.add(historial)

    if gerente_de(usuario) is not None:
        registrar_auditoria(
            db, usuario, Accion.CONTRASENA_RESTABLECIDA, "usuario", usuario.id, origen=origen
        )

    db.commit()
    return "Contraseña restablecida exitosamente. Ya puedes iniciar sesión con tu nueva contraseña."
