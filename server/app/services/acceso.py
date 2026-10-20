"""Ingreso al sistema (H01): credenciales, bloqueo por intentos y estado de cuenta.

Un intento fallido de una cuenta conocida se confirma con commit antes de lanzar el error: si no,
la sesión se cierra sin confirmar y se pierden el contador, el bloqueo y el evento de auditoría.
"""

import hashlib
import logging
import math
import secrets
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import StrEnum

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.dependencias import Origen, gerente_de
from app.core.email import enviar_correo
from app.core.errores import ErrorApi
from app.core.seguridad import HASH_RELLENO, verificar_contrasena
from app.models import TokenRestablecimiento, Usuario
from app.services.auditoria import Accion, registrar_auditoria, registrar_login_desconocido
from app.services.contrasenas import actualizar_contrasena, es_reutilizada

logger = logging.getLogger(__name__)


VIGENCIA_RECUPERACION = timedelta(minutes=30)


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
    "Si el usuario existe y tiene un correo registrado, te enviamos un enlace para restablecer "
    "la contraseña. Revisa tu bandeja de entrada y la carpeta de spam. Si no llega, la asistente "
    "puede pedir al gerente que la restablezca."
)


@dataclass(frozen=True)
class CorreoRecuperacion:
    """Correo pendiente de envío. No se imprime: lleva la dirección y el token."""

    destinatario: str = field(repr=False)
    nombre: str = field(repr=False)
    token: str = field(repr=False)


def solicitar_recuperacion(db: Session, username: str) -> CorreoRecuperacion | None:
    """Crea el token de un solo uso para el usuario y devuelve el correo a enviar. Sin usuario,
    o si está inactivo, eliminado o sin correo, no crea nada, no audita y devuelve None. El
    username escrito no se guarda en ningún registro: puede ser una cuenta ajena o una
    contraseña escrita en el campo equivocado."""
    usuario = db.scalar(
        select(Usuario).where(func.lower(Usuario.username) == func.lower(username)).limit(1)
    )
    if (
        usuario is None
        or usuario.eliminado_en is not None
        or usuario.estado != "activa"
        or not usuario.correo
    ):
        return None

    token_crudo = secrets.token_urlsafe(32)
    db.add(
        TokenRestablecimiento(
            usuario_id=usuario.id,
            token_hash=hashlib.sha256(token_crudo.encode()).hexdigest(),
            expira_en=datetime.now(UTC) + VIGENCIA_RECUPERACION,
        )
    )
    db.commit()
    return CorreoRecuperacion(usuario.correo, usuario.nombres or usuario.username, token_crudo)


def enviar_recuperacion(correo: CorreoRecuperacion) -> None:
    """Envía el correo de recuperación. Un fallo se registra sin usuario ni correo y no cambia
    lo que ya respondió la solicitud."""
    enlace = f"{settings.url_cliente.rstrip('/')}/restablecer/{correo.token}"
    minutos = int(VIGENCIA_RECUPERACION.total_seconds() // 60)
    cuerpo = (
        f"Hola {correo.nombre},\n\n"
        f"Recibimos una solicitud para restablecer tu contraseña.\n"
        f"Abre este enlace para elegir una nueva:\n\n{enlace}\n\n"
        f"El enlace sirve una sola vez y vence en {minutos} minutos.\n"
        f"Si no solicitaste este cambio, puedes ignorar este mensaje.\n"
    )
    if not enviar_correo(correo.destinatario, "Restablecimiento de contraseña", cuerpo):
        logger.warning("No se envió el correo de recuperación de contraseña")


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

    usuario = db.scalar(
        select(Usuario)
        .where(Usuario.id == registro.usuario_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if usuario is None or usuario.eliminado_en is not None or usuario.estado != "activa":
        raise ErrorApi(400, "TOKEN_INVALIDO", "El token de restablecimiento es inválido o expiró.")

    if es_reutilizada(db, usuario, nueva_contrasena):
        raise ErrorApi(
            400,
            "CONTRASENA_REPETIDA",
            "La nueva contraseña no puede ser igual a la actual ni a las últimas 3.",
            "nueva_contrasena",
        )

    registro.usado_en = ahora
    actualizar_contrasena(db, usuario, nueva_contrasena)
    usuario.intentos_fallidos = 0
    usuario.bloqueado_hasta = None

    if gerente_de(usuario) is not None:
        registrar_auditoria(
            db, usuario, Accion.CONTRASENA_RESTABLECIDA, "usuario", usuario.id, origen=origen
        )

    db.commit()
    return "Contraseña restablecida exitosamente. Ya puedes iniciar sesión con tu nueva contraseña."
