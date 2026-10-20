"""Esquemas para la creación y gestión de asistentes (TASK-13).

CA04: Solo se piden nombres y apellidos; el resto de datos los completa la asistente.
CA08: Las credenciales se muestran una sola vez al crearse la cuenta.
"""

import uuid
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, StringConstraints

from app.schemas.usuarios import PATRON_LETRAS

PATRON_USERNAME = r"^[a-zA-Z0-9._-]+$"


class CrearAsistenteEntrada(BaseModel):
    """Datos necesarios para crear una cuenta de asistente (CA04)."""

    nombres: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=1, pattern=PATRON_LETRAS),
    ]
    apellidos: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=1, pattern=PATRON_LETRAS),
    ]
    username: (
        Annotated[
            str,
            StringConstraints(
                strip_whitespace=True, min_length=3, max_length=30, pattern=PATRON_USERNAME
            ),
        ]
        | None
    ) = None
    contrasena: (
        Annotated[
            str,
            StringConstraints(min_length=8, max_length=72),
        ]
        | None
    ) = None
    activar_ahora: bool = True


class DisponibilidadUsernameSalida(BaseModel):
    """Respuesta a la consulta de disponibilidad de un nombre de usuario."""

    disponible: bool
    username: str
    sugerencia: str | None = None


class AsistenteCreadaSalida(BaseModel):
    """Credenciales y datos de la asistente creada, devueltos una sola vez (CA08)."""

    id: uuid.UUID
    nombres: str
    apellidos: str
    username: str
    estado: str
    contrasena: str
    contrasena_inicial: bool
    creado_en: datetime

    model_config = {"from_attributes": True}
