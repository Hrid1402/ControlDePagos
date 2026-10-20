"""Acceso (H01): login con bloqueo por intentos y estado de cuenta, renovación de la sesión y
usuario de la sesión.

Errores del login: 401 CREDENCIALES_INVALIDAS (genérico), 423 CUENTA_BLOQUEADA con los minutos
restantes en detail y 403 CUENTA_INACTIVA.
"""

from fastapi import APIRouter, BackgroundTasks

from app.core.dependencias import OrigenSolicitud, SesionDb, UsuarioActual
from app.core.seguridad import crear_token
from app.models import Usuario
from app.schemas.acceso import (
    IngresoEntrada,
    MensajeSalida,
    RestablecerContrasenaEntrada,
    SesionSalida,
    SolicitudRecuperacion,
    UsuarioSesion,
)
from app.services.acceso import (
    MENSAJE_RECUPERACION_GENERICO,
    enviar_recuperacion,
    iniciar_sesion,
    restablecer_contrasena,
    solicitar_recuperacion,
)
from app.services.auditoria import nombre_de

router = APIRouter(prefix="/auth", tags=["acceso"])


def usuario_sesion(usuario: Usuario) -> UsuarioSesion:
    return UsuarioSesion(id=usuario.id, nombre=nombre_de(usuario), rol=usuario.rol)


def sesion_de(usuario: Usuario) -> SesionSalida:
    return SesionSalida(access_token=crear_token(usuario), usuario=usuario_sesion(usuario))


@router.post("/login")
def login(datos: IngresoEntrada, db: SesionDb, origen: OrigenSolicitud) -> SesionSalida:
    usuario = iniciar_sesion(db, datos.username, datos.contrasena, origen)
    return sesion_de(usuario)


@router.post("/renovar")
def renovar(usuario: UsuarioActual) -> SesionSalida:
    """Emite un token nuevo de 30 minutos a partir de uno vigente: el cliente lo pide al pulsar
    continuar o con actividad cerca del vencimiento. Un token vencido, revocado o de una cuenta
    inactiva responde 401 y lleva al login."""
    return sesion_de(usuario)


@router.get("/me")
def yo(usuario: UsuarioActual) -> UsuarioSesion:
    """Usuario de la sesión. El cliente lo pide al recargar para confirmar que el token guardado
    sigue siendo válido."""
    return usuario_sesion(usuario)


@router.post("/recuperar-contrasena")
def recuperar(datos: SolicitudRecuperacion, db: SesionDb, tareas: BackgroundTasks) -> MensajeSalida:
    """Envía el enlace de restablecimiento al correo del usuario si puede recibirlo. La respuesta
    es siempre la misma y el correo sale después de responder: no revela si el usuario existe, está
    activo o tiene correo, ni por el mensaje ni por el tiempo."""
    correo = solicitar_recuperacion(db, datos.username)
    if correo is not None:
        tareas.add_task(enviar_recuperacion, correo)
    return MensajeSalida(detail=MENSAJE_RECUPERACION_GENERICO)


@router.post("/restablecer-contrasena")
def restablecer(
    datos: RestablecerContrasenaEntrada, db: SesionDb, origen: OrigenSolicitud
) -> MensajeSalida:
    """Restablece la contraseña utilizando el token recibido por correo."""
    detalle = restablecer_contrasena(db, datos.token, datos.nueva_contrasena, origen)
    return MensajeSalida(detail=detalle)
