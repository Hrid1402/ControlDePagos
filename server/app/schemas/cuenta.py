from typing import Annotated

from pydantic import BaseModel, StringConstraints

from app.core.reglas import ContrasenaNueva, Username


class CambiarUsuarioEntrada(BaseModel):
    """Usuario nuevo con el que se ingresa al sistema."""

    username: Username


class UsuarioCambiadoSalida(BaseModel):
    username: str
    cambios_restantes: int
    aviso: str


class CambiarContrasenaEntrada(BaseModel):
    """Contraseña actual y nueva. Ninguna se recorta: los espacios son parte de ellas."""

    contrasena_actual: Annotated[str, StringConstraints(min_length=1)]
    contrasena_nueva: ContrasenaNueva
