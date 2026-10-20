from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

TAMANO_POR_DEFECTO = 20
TAMANO_MAXIMO = 100


@dataclass(frozen=True)
class Paginacion:
    page: int
    size: int

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.size


def paginacion(
    page: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1, le=TAMANO_MAXIMO)] = TAMANO_POR_DEFECTO,
) -> Paginacion:
    return Paginacion(page=page, size=size)


ParametrosPagina = Annotated[Paginacion, Depends(paginacion)]


class Pagina[T](BaseModel):
    """Página de resultados. Admite modelos del ORM: el router los convierte a su esquema de
    salida declarando response_model=Pagina[EsquemaSalida]."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    items: list[T]
    total: int
    page: int


def paginar[M](db: Session, consulta: Select[M], parametros: Paginacion) -> Pagina[M]:
    """Cuenta el total sobre el filtro completo y devuelve una página con orden estable.

    La consulta debe incluir la columna id: se agrega al final del ORDER BY como desempate,
    o como único orden si la consulta no trae uno.
    """
    total = db.scalar(select(func.count()).select_from(consulta.order_by(None).subquery()))
    pagina = (
        consulta.order_by(consulta.selected_columns["id"])
        .offset(parametros.offset)
        .limit(parametros.size)
    )
    return Pagina(items=list(db.scalars(pagina)), total=total or 0, page=parametros.page)
