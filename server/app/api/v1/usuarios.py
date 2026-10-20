"""Endpoints para gestión del perfil del usuario y política de privacidad (TASK-4).

CA01: Nombres y apellidos obligatorios; solo letras, con tildes y ñ.
CA06: Celular obligatorio de 9 dígitos que empieza con 9.
CA09: El rol se muestra pero no se puede editar.
CA11: Cada usuario solo ve y edita sus propios datos.
"""

from fastapi import APIRouter

from app.core.dependencias import OrigenSolicitud, SesionDb, UsuarioActual
from app.schemas.usuarios import (
    AceptarPoliticaEntrada,
    ActualizarPerfilEntrada,
    PerfilSalida,
)
from app.services.usuarios import aceptar_politica, actualizar_perfil

router = APIRouter(prefix="/usuarios", tags=["usuarios"])


@router.get("/perfil", response_model=PerfilSalida)
@router.get("/me", response_model=PerfilSalida, include_in_schema=False)
def obtener_perfil(usuario: UsuarioActual) -> PerfilSalida:
    """Devuelve los datos del perfil del usuario autenticado (CA09, CA11)."""
    return PerfilSalida.model_validate(usuario)


@router.put("/perfil", response_model=PerfilSalida)
@router.put("/me", response_model=PerfilSalida, include_in_schema=False)
def editar_perfil(
    datos: ActualizarPerfilEntrada,
    usuario: UsuarioActual,
    db: SesionDb,
    origen: OrigenSolicitud,
) -> PerfilSalida:
    """Actualiza datos personales respetando validaciones de formato e integridad."""
    usuario_actualizado = actualizar_perfil(db, usuario, datos, origen)
    return PerfilSalida.model_validate(usuario_actualizado)


@router.post("/politica", response_model=PerfilSalida)
def registrar_politica(
    datos: AceptarPoliticaEntrada,
    usuario: UsuarioActual,
    db: SesionDb,
    origen: OrigenSolicitud,
) -> PerfilSalida:
    """Registra la aceptación de la versión de política de privacidad."""
    usuario_actualizado = aceptar_politica(db, usuario, datos.version, origen)
    return PerfilSalida.model_validate(usuario_actualizado)
