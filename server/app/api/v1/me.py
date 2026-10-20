"""Cuenta propia (H02, TASK-8): cambio de usuario y de contraseña.

Cada usuario, gerente o asistente, solo actúa sobre su propia cuenta: no reciben ningún id.
"""

from fastapi import APIRouter

from app.api.v1.auth import sesion_de
from app.core.dependencias import OrigenSolicitud, SesionDb, UsuarioActual
from app.schemas.acceso import SesionSalida
from app.schemas.cuenta import (
    CambiarContrasenaEntrada,
    CambiarUsuarioEntrada,
    UsuarioCambiadoSalida,
)
from app.services.cuenta import AVISO_USUARIO_NUEVO, cambiar_contrasena, cambiar_usuario

router = APIRouter(prefix="/me", tags=["cuenta"])


@router.patch("/usuario")
def cambiar_mi_usuario(
    datos: CambiarUsuarioEntrada,
    usuario: UsuarioActual,
    db: SesionDb,
    origen: OrigenSolicitud,
) -> UsuarioCambiadoSalida:
    """Cambia el usuario con el que se ingresa (CA07). Responde 409 LIMITE_EXCEDIDO si ya se
    usaron los 2 cambios del mes y 409 DUPLICADO si el usuario está en uso."""
    restantes = cambiar_usuario(db, usuario, datos.username, origen)
    return UsuarioCambiadoSalida(
        username=usuario.username, cambios_restantes=restantes, aviso=AVISO_USUARIO_NUEVO
    )


@router.post("/contrasena")
def cambiar_mi_contrasena(
    datos: CambiarContrasenaEntrada,
    usuario: UsuarioActual,
    db: SesionDb,
    origen: OrigenSolicitud,
) -> SesionSalida:
    """Cambia la contraseña y cierra las demás sesiones (CA17). Devuelve un token nuevo: el
    cliente debe reemplazar el suyo, porque el anterior queda revocado."""
    actualizado = cambiar_contrasena(
        db, usuario, datos.contrasena_actual, datos.contrasena_nueva, origen
    )
    return sesion_de(actualizado)
