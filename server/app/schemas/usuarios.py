import re
import uuid
from datetime import datetime
from typing import Annotated, Literal, Self

from pydantic import BaseModel, StringConstraints, model_validator

PATRON_LETRAS = r"^[a-zA-ZáéíóúÁÉÍÓÚñÑüÜ\s]+$"
PATRON_CELULAR = r"^9\d{8}$"


class ActualizarPerfilEntrada(BaseModel):
    """Datos personales que el usuario puede editar."""

    nombres: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=1, pattern=PATRON_LETRAS),
    ]
    apellidos: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=1, pattern=PATRON_LETRAS),
    ]
    celular: Annotated[
        str,
        StringConstraints(strip_whitespace=True, pattern=PATRON_CELULAR),
    ]
    correo: str | None = None
    tipo_documento: Literal["dni", "ce", "pasaporte"] | None = None
    numero_documento: str | None = None
    politica_version: str | None = None

    @model_validator(mode="after")
    def validar_documento(self) -> Self:
        if self.tipo_documento is None and self.numero_documento is None:
            return self
        if self.tipo_documento is not None and self.numero_documento is None:
            raise ValueError("Debes ingresar el número de documento.")
        if self.tipo_documento is None and self.numero_documento is not None:
            raise ValueError("Debes seleccionar el tipo de documento.")
        if self.tipo_documento == "dni" and not re.fullmatch(
            r"^\d{8}$", self.numero_documento or ""
        ):
            raise ValueError("El DNI debe tener exactamente 8 dígitos.")
        if self.tipo_documento in ("ce", "pasaporte") and not re.fullmatch(
            r"^[A-Za-z0-9]{9,12}$", self.numero_documento or ""
        ):
            raise ValueError(
                "El carné de extranjería o pasaporte debe tener "
                "entre 9 y 12 caracteres alfanuméricos."
            )
        return self


class AceptarPoliticaEntrada(BaseModel):
    """Confirmación de lectura y aceptación de la política de privacidad."""

    version: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)] = "1.0"


class PerfilSalida(BaseModel):
    """Datos del perfil que el usuario consulta. El rol es visible pero no editable."""

    id: uuid.UUID
    username: str
    rol: str
    nombres: str | None
    apellidos: str | None
    celular: str | None
    correo: str | None
    tipo_documento: str | None
    numero_documento: str | None
    politica_version: str | None
    politica_aceptada_en: datetime | None

    model_config = {"from_attributes": True}
