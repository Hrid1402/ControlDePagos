from typing import Annotated

from pydantic import BaseModel, StringConstraints, field_validator

# Sin espacios en ningún lugar: el usuario es lo que se escribe para ingresar.
PATRON_USUARIO = r"^\S+$"
LARGO_MAXIMO_USUARIO = 50
# bcrypt rechaza más de 72 bytes (ver hashear_contrasena).
BYTES_MAXIMOS_CONTRASENA = 72


class CambiarUsuarioEntrada(BaseModel):
    """Usuario nuevo con el que se ingresa al sistema."""

    username: Annotated[
        str,
        StringConstraints(
            strip_whitespace=True,
            min_length=1,
            max_length=LARGO_MAXIMO_USUARIO,
            pattern=PATRON_USUARIO,
        ),
    ]


class UsuarioCambiadoSalida(BaseModel):
    username: str
    cambios_restantes: int
    aviso: str


class CambiarContrasenaEntrada(BaseModel):
    """Contraseña actual y nueva. Ninguna se recorta: los espacios son parte de ellas."""

    contrasena_actual: Annotated[str, StringConstraints(min_length=1)]
    contrasena_nueva: Annotated[str, StringConstraints(min_length=1)]

    @field_validator("contrasena_nueva")
    @classmethod
    def validar_largo(cls, valor: str) -> str:
        if len(valor.encode()) > BYTES_MAXIMOS_CONTRASENA:
            raise ValueError("La contraseña es demasiado larga.")
        return valor
