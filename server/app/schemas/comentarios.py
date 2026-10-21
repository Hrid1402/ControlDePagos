"""Comentarios de una deuda (H17 CA06, TASK-54)."""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class ComentarioEntrada(BaseModel):
    texto: str = Field(min_length=1, max_length=500, pattern=r"\S")


class ComentarioSalida(BaseModel):
    id: uuid.UUID
    texto: str
    autor: str
    rol: str
    propio: bool
    creado_en: datetime
