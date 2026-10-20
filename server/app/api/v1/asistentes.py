"""Endpoints para la gestión y creación de asistentes por parte del gerente (TASK-13).

CA04: Solo nombres y apellidos son requeridos al crear la asistente.
CA08: Las credenciales se muestran una sola vez al crearse la cuenta.
"""

from typing import Annotated

from fastapi import APIRouter, Query, status

from app.core.dependencias import OrigenSolicitud, SesionDb, SoloGerente
from app.schemas.asistentes import (
    AsistenteCreadaSalida,
    CrearAsistenteEntrada,
    DisponibilidadUsernameSalida,
)
from app.services.asistentes import (
    crear_asistente,
    verificar_disponibilidad_username,
)

router = APIRouter(prefix="/asistentes", tags=["asistentes"])


@router.get("/disponibilidad", response_model=DisponibilidadUsernameSalida)
def consultar_disponibilidad(
    username: Annotated[str, Query(min_length=3, max_length=30)],
    _gerente: SoloGerente,
    db: SesionDb,
) -> DisponibilidadUsernameSalida:
    """Verifica si un nombre de usuario está disponible para una nueva asistente."""
    return verificar_disponibilidad_username(db, username)


@router.post(
    "",
    response_model=AsistenteCreadaSalida,
    status_code=status.HTTP_201_CREATED,
)
def registrar_asistente(
    datos: CrearAsistenteEntrada,
    gerente: SoloGerente,
    db: SesionDb,
    origen: OrigenSolicitud,
) -> AsistenteCreadaSalida:
    """Crea una nueva cuenta de asistente para el gerente autenticado (CA04, CA08)."""
    asistente, contrasena_plana = crear_asistente(db, gerente, datos, origen)
    return AsistenteCreadaSalida(
        id=asistente.id,
        nombres=asistente.nombres or "",
        apellidos=asistente.apellidos or "",
        username=asistente.username,
        estado=asistente.estado,
        contrasena=contrasena_plana,
        contrasena_inicial=asistente.contrasena_inicial,
        creado_en=asistente.creado_en,
    )
