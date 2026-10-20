import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import ForeignKey, Index, SmallInteger, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, ConActualizado, ConId


class OrdenPago(ConId, ConActualizado, Base):
    __tablename__ = "orden_pago"
    __table_args__ = (
        Index(
            "uq_orden_pago_abierta",
            "deuda_id",
            unique=True,
            postgresql_where=text("estado IN ('enviada', 'vista', 'aceptada')"),
        ),
    )

    deuda_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("deuda.id"), index=True)
    gerente_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("usuario.id"), index=True)
    asistente_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("usuario.id"), index=True)
    plazo: Mapped[datetime | None]
    mensaje: Mapped[str | None]
    estado: Mapped[str] = mapped_column(server_default=text("'enviada'"))
    motivo_rechazo: Mapped[str | None]
    reenvios: Mapped[int] = mapped_column(SmallInteger, server_default=text("0"))
    vista_en: Mapped[datetime | None]
    aceptada_en: Mapped[datetime | None]
    pagada_en: Mapped[datetime | None]
    cancelada_en: Mapped[datetime | None]
    # Importe y moneda que el gerente autorizó al ordenar (migración 0004).
    monto: Mapped[Decimal]
    moneda: Mapped[str]


class ReporteProblema(ConId, ConActualizado, Base):
    __tablename__ = "reporte_problema"

    deuda_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("deuda.id"), index=True)
    orden_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("orden_pago.id"), index=True)
    usuario_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("usuario.id"), index=True)
    motivo: Mapped[str]
    detalle: Mapped[str | None]
    resolucion: Mapped[str | None]
    resuelto_por: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("usuario.id"), index=True)
    resuelto_en: Mapped[datetime | None]


class Pago(ConId, ConActualizado, Base):
    __tablename__ = "pago"
    __table_args__ = (
        Index(
            "uq_pago_en_curso",
            "deuda_id",
            unique=True,
            postgresql_where=text("estado IN ('iniciado', 'esperando_confirmacion', 'incierto')"),
        ),
    )

    deuda_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("deuda.id"), index=True)
    medio_pago_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("medio_pago.id"), index=True)
    usuario_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("usuario.id"), index=True)
    monto: Mapped[Decimal]
    moneda: Mapped[str] = mapped_column(server_default=text("'PEN'"))
    comision: Mapped[Decimal] = mapped_column(server_default=text("0"))
    estado: Mapped[str] = mapped_column(server_default=text("'iniciado'"))
    referencia_externa: Mapped[str | None]
    motivo_error: Mapped[str | None]
    constancia_url: Mapped[str | None]
    completado_en: Mapped[datetime | None]


class SolicitudAprobacion(ConId, ConActualizado, Base):
    __tablename__ = "solicitud_aprobacion"
    __table_args__ = (
        Index(
            "uq_solicitud_aprobacion_pendiente",
            "deuda_id",
            unique=True,
            postgresql_where=text("estado = 'pendiente'"),
        ),
    )

    deuda_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("deuda.id"), index=True)
    asistente_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("usuario.id"), index=True)
    monto: Mapped[Decimal]
    moneda: Mapped[str] = mapped_column(server_default=text("'PEN'"))
    estado: Mapped[str] = mapped_column(server_default=text("'pendiente'"))
    motivo: Mapped[str | None]
    recordatorios_enviados: Mapped[int] = mapped_column(SmallInteger, server_default=text("0"))
    resuelta_por: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("usuario.id"), index=True)
    resuelta_en: Mapped[datetime | None]
