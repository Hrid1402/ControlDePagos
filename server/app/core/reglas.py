"""Reglas comunes de username y contraseña para toda cuenta que las fija.

El username sigue a ck_usuario_username: de 3 a 30 caracteres. La contraseña cumple H02 CA13 y
no supera los 72 bytes que admite bcrypt (ver hashear_contrasena): si los superara, el hash
fallaría con un error del servidor en lugar de un error de validación.
"""

from typing import Annotated

from pydantic import AfterValidator, StringConstraints

LARGO_MINIMO_USERNAME = 3
LARGO_MAXIMO_USERNAME = 30
PATRON_USERNAME = r"^[a-zA-Z0-9._-]+$"

LARGO_MINIMO_CONTRASENA = 8
BYTES_MAXIMOS_CONTRASENA = 72


def es_simbolo(caracter: str) -> bool:
    return not caracter.isalnum() and not caracter.isspace()


def validar_contrasena(contrasena: str) -> str:
    """Devuelve la contraseña si cumple las reglas; si no, ValueError con el motivo. El mensaje
    nunca incluye la contraseña."""
    if len(contrasena.encode()) > BYTES_MAXIMOS_CONTRASENA:
        raise ValueError("La contraseña es demasiado larga.")
    if len(contrasena) < LARGO_MINIMO_CONTRASENA:
        raise ValueError(f"La contraseña debe tener al menos {LARGO_MINIMO_CONTRASENA} caracteres.")
    if not (
        any(c.isupper() for c in contrasena)
        and any(c.islower() for c in contrasena)
        and any(c.isdigit() for c in contrasena)
        and any(es_simbolo(c) for c in contrasena)
    ):
        raise ValueError("La contraseña debe tener mayúscula, minúscula, número y símbolo.")
    return contrasena


# Se recortan los espacios de los extremos: no pueden ser parte del username.
Username = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=LARGO_MINIMO_USERNAME,
        max_length=LARGO_MAXIMO_USERNAME,
        pattern=PATRON_USERNAME,
    ),
]

# La contraseña no se recorta: los espacios son parte de ella.
ContrasenaNueva = Annotated[str, AfterValidator(validar_contrasena)]
