"""Cambio de usuario y de contraseña de la cuenta propia (TASK-8, H02).

CA07: el usuario se cambia hasta 2 veces por mes calendario de Lima y no puede repetirse.
CA12: para cambiar la contraseña se pide la actual.
CA16: la nueva no puede ser igual a la actual ni a las últimas 3.
CA17: el cambio incrementa token_version, que cierra las demás sesiones.

Ambos cambios bloquean la fila del usuario con FOR UPDATE hasta el commit: dos solicitudes
simultáneas de la misma cuenta se hacen en fila y la segunda ve el resultado de la primera.
"""

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.dependencias import Origen
from app.core.errores import ErrorApi
from app.core.seguridad import verificar_contrasena
from app.core.tiempo import ahora_lima
from app.models import CambioUsuario, Usuario
from app.services.auditoria import Accion, diferencias, registrar_auditoria
from app.services.contrasenas import (
    CONTRASENAS_ANTERIORES,
    actualizar_contrasena,
    es_reutilizada,
)

CAMBIOS_USUARIO_POR_MES = 2
AVISO_USUARIO_NUEVO = "Desde ahora debes ingresar con tu nuevo usuario."


def inicio_de_mes(ahora: datetime) -> datetime:
    """Primer instante del mes de ahora en su misma zona horaria."""
    return ahora.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def cambios_restantes(db: Session, usuario: Usuario, ahora: datetime | None = None) -> int:
    """Cambios de usuario que quedan en el mes en curso de Lima (CA07). También los necesita el
    perfil para mostrar cuántos quedan."""
    desde = inicio_de_mes(ahora or ahora_lima())
    hechos = db.scalar(
        select(func.count())
        .select_from(CambioUsuario)
        .where(CambioUsuario.usuario_id == usuario.id, CambioUsuario.creado_en >= desde)
    )
    return max(0, CAMBIOS_USUARIO_POR_MES - (hechos or 0))


def bloquear(db: Session, usuario: Usuario) -> None:
    """Toma el bloqueo de la fila y la vuelve a leer: si otra solicitud la cambió antes, aquí se
    ve el valor confirmado y no el que tenía el objeto al autenticar."""
    db.scalar(
        select(Usuario)
        .where(Usuario.id == usuario.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )


def usuario_duplicado() -> ErrorApi:
    return ErrorApi(409, "DUPLICADO", "Ese usuario ya está en uso.", "username")


def cambiar_usuario(
    db: Session,
    usuario: Usuario,
    nuevo: str,
    origen: Origen,
    ahora: datetime | None = None,
) -> int:
    """Cambia el usuario con el que se ingresa y devuelve los cambios que quedan en el mes."""
    bloquear(db, usuario)

    anterior = usuario.username
    if nuevo.lower() == anterior.lower():
        # Cambiar solo las mayúsculas sigue siendo el mismo usuario: no gasta un cambio.
        raise ErrorApi(422, "VALIDACION", "El nuevo usuario es igual al actual.", "username")
    if cambios_restantes(db, usuario, ahora) == 0:
        raise ErrorApi(
            409,
            "LIMITE_EXCEDIDO",
            f"Ya cambiaste tu usuario {CAMBIOS_USUARIO_POR_MES} veces este mes.",
            "username",
        )
    # uq_usuario_username no es parcial: también cuentan los usuarios de cuentas eliminadas.
    en_uso = db.scalar(
        select(Usuario.id).where(
            func.lower(Usuario.username) == nuevo.lower(), Usuario.id != usuario.id
        )
    )
    if en_uso is not None:
        raise usuario_duplicado()

    try:
        with db.begin_nested():
            db.add(CambioUsuario(usuario_id=usuario.id, anterior=anterior, nuevo=nuevo))
            usuario.username = nuevo
            db.flush()
    except IntegrityError as error:
        # Otra cuenta tomó el mismo usuario entre la consulta y el guardado.
        if "uq_usuario_username" not in str(error.orig):
            raise
        db.expire(usuario)
        raise usuario_duplicado() from error

    registrar_auditoria(
        db,
        usuario,
        Accion.USUARIO_CAMBIADO,
        "usuario",
        usuario.id,
        diferencias({"username": anterior}, {"username": nuevo}),
        origen=origen,
    )
    db.commit()
    return cambios_restantes(db, usuario, ahora)


def contrasena_repetida() -> ErrorApi:
    return ErrorApi(
        422,
        "CONTRASENA_REPETIDA",
        "La nueva contraseña no puede ser igual a la actual ni a las últimas "
        f"{CONTRASENAS_ANTERIORES}.",
        "contrasena_nueva",
    )


def cambiar_contrasena(
    db: Session, usuario: Usuario, actual: str, nueva: str, origen: Origen
) -> Usuario:
    """Cambia la contraseña y sube token_version: los tokens emitidos antes quedan revocados.
    Quien llama debe devolver un token nuevo para que la sesión actual siga abierta."""
    bloquear(db, usuario)

    if not verificar_contrasena(actual, usuario.password_hash):
        raise ErrorApi(
            422,
            "CONTRASENA_INCORRECTA",
            "La contraseña actual no es correcta.",
            "contrasena_actual",
        )

    if es_reutilizada(db, usuario, nueva):
        raise contrasena_repetida()

    version = usuario.token_version
    actualizar_contrasena(db, usuario, nueva)

    registrar_auditoria(
        db,
        usuario,
        Accion.CONTRASENA_CAMBIADA,
        "usuario",
        usuario.id,
        diferencias({"token_version": version}, {"token_version": usuario.token_version}),
        origen=origen,
    )
    db.commit()
    return usuario
