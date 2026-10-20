"""Datos del gerente que recibe el comando de inicialización (TASK-27).

Solo el username es obligatorio. Nombres, apellidos y correo los completa el gerente en Mi
cuenta (H02); el correo es el que habilita la recuperación de contraseña (H01).
"""

from typing import Annotated

from pydantic import BaseModel, EmailStr, StringConstraints

from app.core.reglas import Username
from app.schemas.usuarios import PATRON_LETRAS

Letras = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, pattern=PATRON_LETRAS)
]


class DatosGerente(BaseModel):
    username: Username
    nombres: Letras | None = None
    apellidos: Letras | None = None
    correo: EmailStr | None = None
