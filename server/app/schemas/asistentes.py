"""Esquemas para la creación y gestión de asistentes (TASK-13).

CA04: Solo se piden nombres y apellidos; el resto de datos los completa la asistente.
CA08: Las credenciales se muestran una sola vez al crearse la cuenta.
"""

import uuid
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, StringConstraints

from app.core.reglas import ContrasenaNueva, Username
from app.schemas.usuarios import PATRON_LETRAS


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
    username: Username | None = None
    contrasena: ContrasenaNueva | None = None
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


class AsistenteResumen(BaseModel):
    """Cuenta de asistente tal como queda tras una acción del gerente (TASK-14)."""

    id: uuid.UUID
    nombres: str | None
    apellidos: str | None
    username: str
    estado: str

    model_config = {"from_attributes": True}


class ActivacionSalida(BaseModel):
    """Resultado de activar una cuenta (CA10 y CA14). desactivada es la que estaba activa."""

    activada: AsistenteResumen
    desactivada: AsistenteResumen | None
    ordenes_traspasadas: list[uuid.UUID]


class DesactivacionSalida(BaseModel):
    """Resultado de desactivar una cuenta (CA11 a CA14). sesiones_cerradas confirma al gerente que
    la asistente ya no puede seguir trabajando con una sesión abierta."""

    asistente: AsistenteResumen
    sesiones_cerradas: bool
    sin_asistente_activa: bool
    aviso: str | None
    ordenes_canceladas: list[uuid.UUID]


class ContrasenaRestablecidaSalida(BaseModel):
    """Contraseña nueva de la asistente, devuelta una sola vez (CA16)."""

    id: uuid.UUID
    username: str
    contrasena: str
    contrasena_inicial: bool


class AsistenteListaSalida(AsistenteResumen):
    """Fila de la lista de asistentes (CA01): nombre, usuario, estado y último ingreso."""

    ultimo_ingreso: datetime | None
    creado_en: datetime


class EventoActivacion(BaseModel):
    """Un cambio de estado de la cuenta (CA17). realizada_por es el nombre de quien lo hizo,
    conservado aunque esa cuenta se haya eliminado."""

    accion: str
    realizada_por: str
    creado_en: datetime


class AsistenteDetalleSalida(AsistenteListaSalida):
    """Detalle de una cuenta con su historial de activaciones, del más reciente al más antiguo."""

    historial: list[EventoActivacion]
