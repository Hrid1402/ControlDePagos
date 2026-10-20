"""Búsqueda de texto sin distinguir mayúsculas, compartida por los listados."""

from typing import Any

from sqlalchemy import ColumnElement
from sqlalchemy.sql.elements import SQLCoreOperations

ESCAPE = "\\"


def patron_contiene(texto: str) -> str:
    """Patrón ILIKE que encuentra el texto en cualquier posición. Escapa los comodines: «50%» y
    «a_b» se buscan tal cual, no como cualquier carácter."""
    escapado = texto.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escapado}%"


def contiene(columna: SQLCoreOperations[Any], texto: str) -> ColumnElement[bool]:
    return columna.ilike(patron_contiene(texto), escape=ESCAPE)
