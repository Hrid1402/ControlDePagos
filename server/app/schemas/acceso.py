import uuid
from typing import Annotated, Literal

from pydantic import BaseModel, StringConstraints


class IngresoEntrada(BaseModel):
    """Credenciales del login. La contraseña no se recorta: los espacios son parte de ella."""

    username: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
    contrasena: Annotated[str, StringConstraints(min_length=1)]


class UsuarioSesion(BaseModel):
    """Datos del usuario que guarda el cliente junto al token."""

    id: uuid.UUID
    nombre: str
    rol: str


class SesionSalida(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    usuario: UsuarioSesion
