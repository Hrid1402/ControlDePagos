import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, computed_field


class NotificacionSalida(BaseModel):
    """Notificación como la ve su destinatario. leida se deriva de leida_en."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tipo: str
    titulo: str
    mensaje: str
    deuda_id: uuid.UUID | None
    urgente: bool
    leida_en: datetime | None
    creado_en: datetime

    @computed_field  # type: ignore[prop-decorator]
    @property
    def leida(self) -> bool:
        return self.leida_en is not None
