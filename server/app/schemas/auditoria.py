import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel


class RegistroAuditoriaSalida(BaseModel):
    id: uuid.UUID
    gerente_id: uuid.UUID
    usuario_id: uuid.UUID | None
    usuario_nombre: str
    accion: str
    entidad: str
    entidad_id: uuid.UUID | None
    detalle: dict[str, Any]
    dispositivo: str | None
    ip: str | None
    creado_en: datetime
