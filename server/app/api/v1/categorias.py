"""Endpoints para la gestión de categorías con permisos por rol (H09, TASK-28).

CA04: Gerente y asistente pueden crear categorías; solo el gerente las edita y elimina.
CA05: Solo se puede eliminar una categoría sin servicios; si tiene, primero se mueven a otra.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Query, status

from app.core.dependencias import (
    GerenteId,
    OrigenSolicitud,
    SesionDb,
    SoloGerente,
    UsuarioActual,
)
from app.schemas.categorias import (
    ActualizarCategoriaEntrada,
    CategoriaSalida,
    CrearCategoriaEntrada,
    MensajeEliminacionCategoria,
    MoverServiciosEntrada,
)
from app.services.categorias import (
    actualizar_categoria,
    crear_categoria,
    eliminar_categoria,
    listar_categorias,
    mover_servicios,
    obtener_categoria,
)

router = APIRouter(prefix="/categorias", tags=["categorias"])


@router.get("", response_model=list[CategoriaSalida])
def listar(
    db: SesionDb,
    _usuario: UsuarioActual,
    gerente_id: GerenteId,
) -> list[CategoriaSalida]:
    """Lista las categorías del gerente con sus conteos de servicios (gerente o asistente)."""
    return listar_categorias(db, gerente_id)


@router.get("/{id}", response_model=CategoriaSalida)
def detalle(
    id: uuid.UUID,
    db: SesionDb,
    _usuario: UsuarioActual,
    gerente_id: GerenteId,
) -> CategoriaSalida:
    """Obtiene el detalle de una categoría específica con su conteo de servicios."""
    return obtener_categoria(db, gerente_id, id)


@router.post("", response_model=CategoriaSalida, status_code=status.HTTP_201_CREATED)
def crear(
    datos: CrearCategoriaEntrada,
    db: SesionDb,
    usuario: UsuarioActual,
    gerente_id: GerenteId,
    origen: OrigenSolicitud,
) -> CategoriaSalida:
    """Crea una nueva categoría (CA04: permitido a gerente y asistente)."""
    return crear_categoria(db, usuario, gerente_id, datos, origen)


@router.put("/{id}", response_model=CategoriaSalida)
def editar(
    id: uuid.UUID,
    datos: ActualizarCategoriaEntrada,
    db: SesionDb,
    gerente: SoloGerente,
    gerente_id: GerenteId,
    origen: OrigenSolicitud,
) -> CategoriaSalida:
    """Edita los datos de una categoría (CA04: exclusivo del gerente)."""
    return actualizar_categoria(db, gerente, gerente_id, id, datos, origen)


@router.post("/{id}/mover-servicios", response_model=MensajeEliminacionCategoria)
def traspasar_servicios(
    id: uuid.UUID,
    datos: MoverServiciosEntrada,
    db: SesionDb,
    gerente: SoloGerente,
    gerente_id: GerenteId,
    origen: OrigenSolicitud,
) -> MensajeEliminacionCategoria:
    """Mueve todos los servicios de esta categoría a otra (CA05: exclusivo del gerente)."""
    movidos = mover_servicios(db, gerente, gerente_id, id, datos.destino_id, origen)
    return MensajeEliminacionCategoria(
        mensaje=f"Se movieron {movidos} servicios exitosamente.",
        servicios_movidos=movidos,
    )


@router.delete("/{id}", response_model=MensajeEliminacionCategoria)
def eliminar(
    id: uuid.UUID,
    db: SesionDb,
    gerente: SoloGerente,
    gerente_id: GerenteId,
    origen: OrigenSolicitud,
    mover_a: Annotated[
        uuid.UUID | None,
        Query(
            description=("Categoría destino para los servicios asociados antes de eliminar (CA05).")
        ),
    ] = None,
) -> MensajeEliminacionCategoria:
    """Elimina una categoría sin servicios o trasvasándolos a mover_a (CA04, CA05: solo gerente)."""
    return eliminar_categoria(db, gerente, gerente_id, id, mover_a, origen)
