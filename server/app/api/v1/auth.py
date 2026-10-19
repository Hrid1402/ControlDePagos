"""Acceso (H01): login con bloqueo por intentos y estado de cuenta.

Errores del login: 401 CREDENCIALES_INVALIDAS (genérico), 423 CUENTA_BLOQUEADA con los minutos
restantes en detail y 403 CUENTA_INACTIVA.
"""

from fastapi import APIRouter

from app.core.dependencias import OrigenSolicitud, SesionDb
from app.core.seguridad import crear_token
from app.models import Usuario
from app.schemas.acceso import IngresoEntrada, SesionSalida, UsuarioSesion
from app.services.acceso import iniciar_sesion
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
