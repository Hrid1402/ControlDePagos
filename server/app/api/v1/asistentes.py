"""Endpoints para la gestión y creación de asistentes por parte del gerente (TASK-13 y TASK-14).

CA04: Solo nombres y apellidos son requeridos al crear la asistente.
CA08: Las credenciales se muestran una sola vez al crearse la cuenta.
CA10 a CA16: activar, desactivar, eliminar y restablecer la contraseña de una cuenta.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Query, status

from app.core.dependencias import OrigenSolicitud, SesionDb, SoloGerente
from app.schemas.asistentes import (
    ActivacionSalida,
    AsistenteCreadaSalida,
    AsistenteResumen,
    ContrasenaRestablecidaSalida,
    CrearAsistenteEntrada,
    DesactivacionSalida,
    DisponibilidadUsernameSalida,
)
from app.services.asistentes import (
    AVISO_SIN_ASISTENTE,
    activar_asistente,
    crear_asistente,
    desactivar_asistente,
    eliminar_asistente,
    restablecer_contrasena_asistente,
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


@router.post("/{asistente_id}/activar", response_model=ActivacionSalida)
def activar(
    asistente_id: uuid.UUID,
    gerente: SoloGerente,
    db: SesionDb,
    origen: OrigenSolicitud,
) -> ActivacionSalida:
    """Activa la cuenta, desactiva la actual y le traspasa sus órdenes sin atender (CA10, CA14)."""
    resultado = activar_asistente(db, gerente, asistente_id, origen)
    desactivada = resultado.desactivada
    return ActivacionSalida(
        activada=AsistenteResumen.model_validate(resultado.activada),
        desactivada=AsistenteResumen.model_validate(desactivada) if desactivada else None,
        ordenes_traspasadas=[orden.id for orden in resultado.ordenes_traspasadas],
    )


@router.post("/{asistente_id}/desactivar", response_model=DesactivacionSalida)
def desactivar(
    asistente_id: uuid.UUID,
    gerente: SoloGerente,
    db: SesionDb,
    origen: OrigenSolicitud,
) -> DesactivacionSalida:
    """Bloquea el acceso y cierra sus sesiones; sin asistente activa, cancela sus órdenes sin
    atender (CA11 a CA14)."""
    resultado = desactivar_asistente(db, gerente, asistente_id, origen)
    return DesactivacionSalida(
        asistente=AsistenteResumen.model_validate(resultado.asistente),
        sesiones_cerradas=True,
        sin_asistente_activa=resultado.sin_asistente_activa,
        aviso=AVISO_SIN_ASISTENTE if resultado.sin_asistente_activa else None,
        ordenes_canceladas=[orden.id for orden in resultado.ordenes_canceladas],
    )


@router.delete("/{asistente_id}", status_code=status.HTTP_204_NO_CONTENT)
def eliminar(
    asistente_id: uuid.UUID,
    gerente: SoloGerente,
    db: SesionDb,
    origen: OrigenSolicitud,
) -> None:
    """Elimina una cuenta inactiva; su nombre se conserva en el historial (CA15)."""
    eliminar_asistente(db, gerente, asistente_id, origen)


@router.post("/{asistente_id}/restablecer-contrasena", response_model=ContrasenaRestablecidaSalida)
def restablecer_contrasena(
    asistente_id: uuid.UUID,
    gerente: SoloGerente,
    db: SesionDb,
    origen: OrigenSolicitud,
) -> ContrasenaRestablecidaSalida:
    """Genera una contraseña nueva, la devuelve una sola vez y cierra sus sesiones (CA16)."""
    asistente, contrasena_plana = restablecer_contrasena_asistente(
        db, gerente, asistente_id, origen
    )
    return ContrasenaRestablecidaSalida(
        id=asistente.id,
        username=asistente.username,
        contrasena=contrasena_plana,
        contrasena_inicial=asistente.contrasena_inicial,
    )
