"""Esquemas para la gestión de categorías de servicios (H09, TASK-28).

CA04: Gerente y asistente pueden crear categorías; solo el gerente las edita y elimina.
CA05: Solo se puede eliminar una categoría sin servicios; si tiene, primero se mueven a otra.
"""

import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, StringConstraints

TipoCategoria = Literal["servicio_variable", "monto_fijo", "tarjeta", "prestamo"]
NombreCategoria = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=40)
]
ColorHex = Annotated[str, StringConstraints(strip_whitespace=True, pattern=r"^#[0-9A-Fa-f]{6}$")]
IconoCategoria = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=50)
]


class CrearCategoriaEntrada(BaseModel):
    """Datos para crear una categoría nueva (gerente o asistente, CA04)."""

    nombre: NombreCategoria
    color: ColorHex = "#64748B"
    icono: IconoCategoria = "pi-tag"
    tipo: TipoCategoria


class ActualizarCategoriaEntrada(BaseModel):
    """Datos para editar una categoría existente (solo gerente, CA04)."""

    nombre: NombreCategoria
    color: ColorHex | None = None
    icono: IconoCategoria | None = None
    tipo: TipoCategoria | None = None


class MoverServiciosEntrada(BaseModel):
    """Identificador de la categoría destino a la que se traspasarán los servicios (CA05)."""

    destino_id: uuid.UUID


class CategoriaSalida(BaseModel):
    """Datos de una categoría, incluyendo el conteo de servicios asociados."""

    id: uuid.UUID
    nombre: str
    color: str
    icono: str
    tipo: str
    precargada: bool
    cantidad_servicios: int = 0
    creado_por: uuid.UUID | None = None
    creado_en: datetime
    actualizado_en: datetime

    model_config = {"from_attributes": True}


class MensajeEliminacionCategoria(BaseModel):
    """Respuesta informativa tras eliminar una categoría."""

    mensaje: str
    servicios_movidos: int = 0
