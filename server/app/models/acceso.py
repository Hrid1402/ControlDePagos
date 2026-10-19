import uuid
from datetime import datetime, time
from ipaddress import IPv4Address, IPv6Address
from typing import Any

from sqlalchemy import ForeignKey, Index, SmallInteger, UniqueConstraint, event, text
from sqlalchemy.dialects.postgresql import INET, JSONB
from sqlalchemy.orm import Mapped, ORMExecuteState, Session, mapped_column

from app.models.base import Base, ConActualizado, ConCreado, ConId


class Usuario(ConId, ConActualizado, Base):
    __tablename__ = "usuario"
    __table_args__ = (
        UniqueConstraint("numero_documento"),
        UniqueConstraint("buzon_recibos"),
        Index("uq_usuario_username", text("lower(username)"), unique=True),
        Index("uq_usuario_correo", text("lower(correo)"), unique=True),
        Index(
            "uq_usuario_asistente_activa",
            "gerente_id",
            unique=True,
            postgresql_where=text(
                "rol = 'asistente' AND estado = 'activa' AND eliminado_en IS NULL"
            ),
        ),
    )

    gerente_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("usuario.id"), index=True)
    rol: Mapped[str]
    username: Mapped[str]
    password_hash: Mapped[str]
    nombres: Mapped[str | None]
    apellidos: Mapped[str | None]
    tipo_documento: Mapped[str | None]
    numero_documento: Mapped[str | None]
    correo: Mapped[str | None]
    celular: Mapped[str | None]
    estado: Mapped[str] = mapped_column(server_default=text("'activa'"))
    contrasena_inicial: Mapped[bool] = mapped_column(server_default=text("true"))
    intentos_fallidos: Mapped[int] = mapped_column(SmallInteger, server_default=text("0"))
    bloqueado_hasta: Mapped[datetime | None]
    token_version: Mapped[int] = mapped_column(server_default=text("0"))
    ultimo_ingreso: Mapped[datetime | None]
    politica_version: Mapped[str | None]
    politica_aceptada_en: Mapped[datetime | None]
    tutorial_completado: Mapped[bool] = mapped_column(server_default=text("false"))
    buzon_recibos: Mapped[str | None]
    horas_recordatorio: Mapped[int] = mapped_column(SmallInteger, server_default=text("4"))
    silencio_desde: Mapped[time | None]
    silencio_hasta: Mapped[time | None]
    resumen_diario_hora: Mapped[time | None]
    reporte_mensual_activo: Mapped[bool] = mapped_column(server_default=text("false"))
    eliminado_en: Mapped[datetime | None]


class HistorialContrasena(ConId, ConCreado, Base):
    __tablename__ = "historial_contrasena"

    usuario_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("usuario.id", ondelete="CASCADE"), index=True
    )
    password_hash: Mapped[str]


class CambioUsuario(ConId, ConCreado, Base):
    __tablename__ = "cambio_usuario"

    usuario_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("usuario.id", ondelete="CASCADE"), index=True
    )
    anterior: Mapped[str]
    nuevo: Mapped[str]


class TokenRestablecimiento(ConId, ConCreado, Base):
    __tablename__ = "token_restablecimiento"
    __table_args__ = (UniqueConstraint("token_hash"),)

    usuario_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("usuario.id", ondelete="CASCADE"), index=True
    )
    token_hash: Mapped[str]
    expira_en: Mapped[datetime]
    usado_en: Mapped[datetime | None]


class ActivacionCuenta(ConId, ConCreado, Base):
    __tablename__ = "activacion_cuenta"

    cuenta_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("usuario.id"), index=True)
    accion: Mapped[str]
    realizada_por: Mapped[uuid.UUID] = mapped_column(ForeignKey("usuario.id"), index=True)


class Auditoria(ConId, ConCreado, Base):
    __tablename__ = "auditoria"
    __table_args__ = (Index("ix_auditoria_gerente_id_creado_en", "gerente_id", "creado_en"),)

    gerente_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("usuario.id"))
    usuario_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("usuario.id", ondelete="SET NULL"), index=True
    )
    usuario_nombre: Mapped[str]
    accion: Mapped[str]
    entidad: Mapped[str]
    entidad_id: Mapped[uuid.UUID | None]
    detalle: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    dispositivo: Mapped[str | None]
    ip: Mapped[IPv4Address | IPv6Address | None] = mapped_column(INET)


class AuditoriaInmutable(Exception):
    """Se intentó editar o borrar un registro de auditoría, que solo admite inserciones."""

    def __init__(self) -> None:
        super().__init__("La auditoría solo admite inserciones: no se edita ni se borra.")


@event.listens_for(Auditoria, "before_update")
@event.listens_for(Auditoria, "before_delete")
def impedir_cambios_por_objeto(*_: object) -> None:
    raise AuditoriaInmutable()


@event.listens_for(Session, "do_orm_execute")
def impedir_cambios_masivos(estado: ORMExecuteState) -> None:
    """Cubre update() y delete() masivos, que no pasan por los eventos del objeto."""
    if (estado.is_update or estado.is_delete) and Auditoria.__mapper__ in estado.all_mappers:
        raise AuditoriaInmutable()
