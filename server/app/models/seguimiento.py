import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import ForeignKey, Index, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, ConActualizado, ConCreado, ConId


class Notificacion(ConId, ConCreado, Base):
    __tablename__ = "notificacion"
    __table_args__ = (Index("ix_notificacion_usuario_id_creado_en", "usuario_id", "creado_en"),)

    usuario_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("usuario.id", ondelete="CASCADE"))
    tipo: Mapped[str]
    titulo: Mapped[str]
    mensaje: Mapped[str]
    deuda_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("deuda.id", ondelete="CASCADE"), index=True
    )
    urgente: Mapped[bool] = mapped_column(server_default=text("false"))
    leida_en: Mapped[datetime | None]


class PreferenciaNotificacion(ConActualizado, Base):
    __tablename__ = "preferencia_notificacion"

    usuario_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("usuario.id", ondelete="CASCADE"), primary_key=True
    )
    tipo: Mapped[str] = mapped_column(primary_key=True)
    canal: Mapped[str] = mapped_column(primary_key=True)
    activa: Mapped[bool] = mapped_column(server_default=text("true"))


class Exportacion(ConId, ConActualizado, Base):
    __tablename__ = "exportacion"

    gerente_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("usuario.id"), index=True)
    usuario_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("usuario.id"), index=True)
    tipo: Mapped[str]
    parametros: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    estado: Mapped[str] = mapped_column(server_default=text("'procesando'"))
    archivo_url: Mapped[str | None]
    expira_en: Mapped[datetime | None]


class EjecucionRobot(ConId, ConCreado, Base):
    __tablename__ = "ejecucion_robot"
    __table_args__ = (Index("ix_ejecucion_robot_empresa_id_creado_en", "empresa_id", "creado_en"),)

    empresa_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("empresa.id"))
    servicio_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("servicio.id", ondelete="SET NULL"), index=True
    )
    deuda_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("deuda.id", ondelete="SET NULL"), index=True
    )
    tarea: Mapped[str]
    estado: Mapped[str] = mapped_column(server_default=text("'en_curso'"))
    detalle: Mapped[str | None]
    terminado_en: Mapped[datetime | None]
