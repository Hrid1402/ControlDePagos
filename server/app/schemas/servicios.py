"""Esquemas de servicios y empresas comunes (H10, TASK-33).

El código de suministro y el nombre de una empresa manual se normalizan en el servicio, no
aquí: ahí se decide si el nombre corresponde a una empresa del catálogo y qué patrón aplica.
"""

import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, StringConstraints, field_validator

LugarPago = Literal["agente_bcp", "agente_kasnet", "ventanilla_empresa", "banca_movil", "otro"]
TipoServicioEmpresa = Literal["luz", "agua", "gas", "telecomunicaciones", "otro"]
FiltroEstado = Literal["activo", "baja", "todos"]

NombreEmpresa = Annotated[str, StringConstraints(strip_whitespace=True, max_length=80)]
CodigoSuministro = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=40)
]
Titular = Annotated[str, StringConstraints(strip_whitespace=True, max_length=120)]
Alias = Annotated[str, StringConstraints(strip_whitespace=True, max_length=60)]
Notas = Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)]


class ServicioEntrada(BaseModel):
    """Datos para crear o editar un servicio. Se indica empresa_id (empresa común, CA01) o
    empresa_nombre ("Otra empresa"), no ambos."""

    categoria_id: uuid.UUID
    empresa_id: uuid.UUID | None = None
    empresa_nombre: NombreEmpresa | None = None
    codigo_suministro: CodigoSuministro
    titular: Titular | None = None
    alias: Alias | None = None
    lugar_pago: LugarPago
    notas: Notas | None = None

    @field_validator("empresa_nombre", "titular", "alias", "notas")
    @classmethod
    def vacio_como_ausente(cls, valor: str | None) -> str | None:
        return valor or None


class EmpresaSalida(BaseModel):
    id: uuid.UUID
    nombre: str
    tipo_servicio: str
    patron_codigo: str | None


class CategoriaServicio(BaseModel):
    id: uuid.UUID
    nombre: str
    tipo: str
    color: str
    icono: str


class ServicioSalida(BaseModel):
    """empresa es el nombre que se muestra; empresa_manual indica que no es del catálogo."""

    id: uuid.UUID
    categoria: CategoriaServicio
    empresa_id: uuid.UUID | None
    empresa: str
    empresa_manual: bool
    codigo_suministro: str
    titular: str | None
    alias: str | None
    lugar_pago: str | None
    notas: str | None
    estado: str
    creado_por: uuid.UUID | None
    creado_en: datetime
    actualizado_en: datetime


class ServicioDetalleSalida(ServicioSalida):
    """deudas_pendientes cuenta las deudas sin pagar ni anular: el formulario advierte con ese
    número antes de cambiar el código (CA07)."""

    deudas_pendientes: int


class AdvertenciasServicio(BaseModel):
    codigo_cambiado: bool
    deudas_pendientes: int


class ServicioEditadoSalida(ServicioSalida):
    advertencias: AdvertenciasServicio
