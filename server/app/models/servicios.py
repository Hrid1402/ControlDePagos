import uuid
from datetime import date, datetime, time
from decimal import Decimal

from sqlalchemy import ForeignKey, Index, LargeBinary, Numeric, SmallInteger, Text, text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, ConActualizado, ConCreado, ConId


class Categoria(ConId, ConActualizado, Base):
    __tablename__ = "categoria"
    __table_args__ = (
        Index("uq_categoria_nombre", "gerente_id", text("lower(nombre)"), unique=True),
    )

    gerente_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("usuario.id"), index=True)
    nombre: Mapped[str]
    color: Mapped[str] = mapped_column(server_default=text("'#64748B'"))
    icono: Mapped[str] = mapped_column(server_default=text("'pi-tag'"))
    tipo: Mapped[str]
    precargada: Mapped[bool] = mapped_column(server_default=text("false"))
    creado_por: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("usuario.id"), index=True)


class Servicio(ConId, ConActualizado, Base):
    __tablename__ = "servicio"
    __table_args__ = (
        Index(
            "uq_servicio_codigo",
            "gerente_id",
            text("coalesce(empresa_id::text, lower(empresa_nombre))"),
            text("upper(codigo_suministro)"),
            unique=True,
            postgresql_where=text("eliminado_en IS NULL"),
        ),
    )

    gerente_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("usuario.id"), index=True)
    categoria_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("categoria.id"), index=True)
    inmueble_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("inmueble.id", ondelete="SET NULL"), index=True
    )
    empresa_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("empresa.id"), index=True)
    empresa_nombre: Mapped[str | None]
    codigo_suministro: Mapped[str]
    titular: Mapped[str | None]
    alias: Mapped[str | None]
    lugar_pago: Mapped[str | None]
    notas: Mapped[str | None]
    medio_pago_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("medio_pago.id", ondelete="SET NULL"), index=True
    )
    portal_usuario_cifrado: Mapped[bytes | None] = mapped_column(LargeBinary)
    portal_clave_cifrada: Mapped[bytes | None] = mapped_column(LargeBinary)
    estado: Mapped[str] = mapped_column(server_default=text("'activo'"))
    creado_por: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("usuario.id"), index=True)
    eliminado_en: Mapped[datetime | None]


class Recurrencia(ConId, ConActualizado, Base):
    __tablename__ = "recurrencia"

    servicio_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("servicio.id", ondelete="CASCADE"), unique=True
    )
    tipo: Mapped[str]
    monto: Mapped[Decimal | None]
    moneda: Mapped[str] = mapped_column(server_default=text("'PEN'"))
    dia_emision: Mapped[int | None] = mapped_column(SmallInteger)
    dia_vencimiento: Mapped[int] = mapped_column(SmallInteger)
    activa: Mapped[bool] = mapped_column(server_default=text("true"))
    ultima_generacion: Mapped[date | None]


class Prestamo(ConId, ConActualizado, Base):
    __tablename__ = "prestamo"

    servicio_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("servicio.id"), index=True)
    monto_total: Mapped[Decimal]
    cuotas_total: Mapped[int] = mapped_column(SmallInteger)
    monto_cuota: Mapped[Decimal]
    fecha_primera_cuota: Mapped[date]
    moneda: Mapped[str] = mapped_column(server_default=text("'PEN'"))


class Deuda(ConId, ConActualizado, Base):
    __tablename__ = "deuda"
    __table_args__ = (
        Index("ix_deuda_gerente_id_estado", "gerente_id", "estado"),
        Index("ix_deuda_gerente_id_fecha_vencimiento", "gerente_id", "fecha_vencimiento"),
        Index(
            "uq_deuda_periodo",
            "servicio_id",
            "periodo",
            text("coalesce(cuota_numero, 0)"),
            unique=True,
            postgresql_where=text("estado <> 'anulada'"),
        ),
    )

    gerente_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("usuario.id"))
    servicio_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("servicio.id"), index=True)
    prestamo_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("prestamo.id"), index=True)
    cuota_numero: Mapped[int | None] = mapped_column(SmallInteger)
    periodo: Mapped[date]
    # NULL solo en esperando_recibo o anulada (ck_deuda_monto): el importe aún no se conoce.
    monto: Mapped[Decimal | None]
    moneda: Mapped[str] = mapped_column(server_default=text("'PEN'"))
    fecha_emision: Mapped[date | None]
    fecha_vencimiento: Mapped[date]
    fecha_estimada: Mapped[date | None]
    numero_recibo: Mapped[str | None]
    recibo_url: Mapped[str | None]
    estado: Mapped[str] = mapped_column(server_default=text("'pendiente'"))
    origen: Mapped[str] = mapped_column(server_default=text("'manual'"))
    fecha_corte: Mapped[date | None]
    pago_minimo: Mapped[Decimal | None]
    pago_total: Mapped[Decimal | None]
    fijada: Mapped[bool] = mapped_column(server_default=text("false"))
    oculta_hasta: Mapped[datetime | None]
    pago_iniciado_en: Mapped[datetime | None]
    pago_iniciado_por: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("usuario.id"), index=True
    )
    pago_realizado: Mapped[bool] = mapped_column(server_default=text("false"))
    recordatorios_enviados: Mapped[int] = mapped_column(SmallInteger, server_default=text("0"))
    pagada_fuera_en: Mapped[datetime | None]
    creado_por: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("usuario.id"), index=True)


class HistorialMonto(ConId, ConCreado, Base):
    __tablename__ = "historial_monto"

    deuda_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("deuda.id", ondelete="CASCADE"), index=True
    )
    monto_anterior: Mapped[Decimal]
    monto_nuevo: Mapped[Decimal]
    origen: Mapped[str]
    usuario_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("usuario.id"), index=True)


class Comentario(ConId, ConCreado, Base):
    __tablename__ = "comentario"

    deuda_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("deuda.id", ondelete="CASCADE"), index=True
    )
    usuario_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("usuario.id"), index=True)
    tipo: Mapped[str] = mapped_column(server_default=text("'texto'"))
    texto: Mapped[str]


class ReglaAlerta(ConId, ConActualizado, Base):
    __tablename__ = "regla_alerta"

    gerente_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("usuario.id"), index=True)
    tipo: Mapped[str] = mapped_column(server_default=text("'vencimiento'"))
    alcance: Mapped[str] = mapped_column(server_default=text("'general'"))
    categoria_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("categoria.id", ondelete="CASCADE"), index=True
    )
    servicio_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("servicio.id", ondelete="CASCADE"), index=True
    )
    dias_antes: Mapped[list[int]] = mapped_column(ARRAY(SmallInteger), server_default=text("'{3}'"))
    porcentaje_aumento: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    canales: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default=text("'{app}'"))
    destinatario: Mapped[str] = mapped_column(server_default=text("'gerente'"))
    hora_envio: Mapped[time] = mapped_column(server_default=text("'08:00'"))
    activa: Mapped[bool] = mapped_column(server_default=text("true"))
