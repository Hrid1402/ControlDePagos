import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import ForeignKey, Index, Numeric, SmallInteger, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, ConActualizado, ConCreado, ConId


class Comprobante(ConId, ConActualizado, Base):
    __tablename__ = "comprobante"
    __table_args__ = (
        Index("ix_comprobante_gerente_id_estado", "gerente_id", "estado"),
        Index(
            "uq_comprobante_hash",
            "hash_sha256",
            unique=True,
            postgresql_where=text("estado <> 'rechazado'"),
        ),
        Index(
            "uq_comprobante_operacion",
            "entidad",
            "numero_operacion",
            unique=True,
            postgresql_where=text("numero_operacion IS NOT NULL AND estado <> 'rechazado'"),
        ),
    )

    gerente_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("usuario.id"))
    archivo_url: Mapped[str]
    archivo_tipo: Mapped[str]
    archivo_bytes: Mapped[int]
    hash_sha256: Mapped[str]
    entidad: Mapped[str | None]
    numero_operacion: Mapped[str | None]
    monto: Mapped[Decimal | None]
    moneda: Mapped[str] = mapped_column(server_default=text("'PEN'"))
    fecha_pago: Mapped[datetime | None]
    texto_ocr: Mapped[str | None]
    confianza: Mapped[Decimal | None] = mapped_column(Numeric(4, 3))
    datos_extraidos: Mapped[dict[str, Any]] = mapped_column(
        JSONB, server_default=text("'{}'::jsonb")
    )
    estado: Mapped[str] = mapped_column(server_default=text("'procesando'"))
    motivo_codigo: Mapped[str | None]
    deuda_sugerida_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("deuda.id", ondelete="SET NULL"), index=True
    )
    fondos: Mapped[str] = mapped_column(server_default=text("'gerente'"))
    reemplaza_a_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("comprobante.id"), index=True
    )
    subido_por: Mapped[uuid.UUID] = mapped_column(ForeignKey("usuario.id"), index=True)
    revisado_por: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("usuario.id"), index=True)
    revisado_en: Mapped[datetime | None]


class ComprobanteDeuda(ConCreado, Base):
    __tablename__ = "comprobante_deuda"

    comprobante_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("comprobante.id", ondelete="CASCADE"), primary_key=True
    )
    deuda_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("deuda.id"), primary_key=True, index=True
    )
    monto_aplicado: Mapped[Decimal]


class Recibo(ConId, ConActualizado, Base):
    __tablename__ = "recibo"
    __table_args__ = (UniqueConstraint("gerente_id", "hash_sha256", "pagina"),)

    gerente_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("usuario.id"))
    archivo_url: Mapped[str]
    archivo_tipo: Mapped[str]
    hash_sha256: Mapped[str]
    pagina: Mapped[int] = mapped_column(SmallInteger, server_default=text("1"))
    origen: Mapped[str]
    estado: Mapped[str] = mapped_column(server_default=text("'procesando'"))
    proveedor_ia: Mapped[str | None]
    datos_extraidos: Mapped[dict[str, Any]] = mapped_column(
        JSONB, server_default=text("'{}'::jsonb")
    )
    propuesta: Mapped[str | None]
    decision: Mapped[str | None]
    servicio_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("servicio.id", ondelete="SET NULL"), index=True
    )
    deuda_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("deuda.id", ondelete="SET NULL"), index=True
    )
    subido_por: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("usuario.id"), index=True)


class CargaQr(ConId, ConCreado, Base):
    __tablename__ = "carga_qr"
    __table_args__ = (UniqueConstraint("token_hash"),)

    usuario_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("usuario.id", ondelete="CASCADE"), index=True
    )
    tipo: Mapped[str]
    deuda_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("deuda.id", ondelete="CASCADE"), index=True
    )
    token_hash: Mapped[str]
    expira_en: Mapped[datetime]
    usado_en: Mapped[datetime | None]


class Conciliacion(ConId, ConCreado, Base):
    __tablename__ = "conciliacion"
    __table_args__ = (UniqueConstraint("gerente_id", "hash_sha256"),)

    gerente_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("usuario.id"))
    medio_pago_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("medio_pago.id"), index=True)
    archivo_url: Mapped[str]
    hash_sha256: Mapped[str]
    periodo: Mapped[date]


class MovimientoConciliacion(ConId, ConActualizado, Base):
    __tablename__ = "movimiento_conciliacion"

    conciliacion_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("conciliacion.id", ondelete="CASCADE"), index=True
    )
    fecha: Mapped[date]
    descripcion: Mapped[str]
    monto: Mapped[Decimal]
    deuda_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("deuda.id", ondelete="SET NULL"), index=True
    )
    estado: Mapped[str] = mapped_column(server_default=text("'sin_deuda'"))
    manual: Mapped[bool] = mapped_column(server_default=text("false"))


class Reembolso(ConId, ConActualizado, Base):
    __tablename__ = "reembolso"

    gerente_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("usuario.id"), index=True)
    asistente_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("usuario.id"), index=True)
    comprobante_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("comprobante.id"), unique=True)
    monto: Mapped[Decimal]
    estado: Mapped[str] = mapped_column(server_default=text("'pendiente'"))
    motivo: Mapped[str | None]
    medio_reembolso: Mapped[str | None]
    resuelto_por: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("usuario.id"), index=True)
    reembolsado_en: Mapped[datetime | None]
