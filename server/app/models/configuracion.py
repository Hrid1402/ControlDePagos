import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import ForeignKey, Index, LargeBinary, SmallInteger, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, ConActualizado, ConId


class MedioPago(ConId, ConActualizado, Base):
    __tablename__ = "medio_pago"
    __table_args__ = (
        Index(
            "uq_medio_pago_alias",
            "gerente_id",
            text("lower(alias)"),
            unique=True,
            postgresql_where=text("eliminado_en IS NULL"),
        ),
        Index(
            "uq_medio_pago_principal",
            "gerente_id",
            unique=True,
            postgresql_where=text("principal AND eliminado_en IS NULL"),
        ),
    )

    gerente_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("usuario.id"), index=True)
    tipo: Mapped[str]
    alias: Mapped[str]
    banco: Mapped[str | None]
    marca: Mapped[str | None]
    ultimos4: Mapped[str | None]
    vencimiento_mes: Mapped[int | None] = mapped_column(SmallInteger)
    vencimiento_anio: Mapped[int | None] = mapped_column(SmallInteger)
    moneda: Mapped[str] = mapped_column(server_default=text("'PEN'"))
    celular: Mapped[str | None]
    token_pasarela: Mapped[str | None]
    principal: Mapped[bool] = mapped_column(server_default=text("false"))
    estado: Mapped[str] = mapped_column(server_default=text("'activo'"))
    eliminado_en: Mapped[datetime | None]


class Limite(ConActualizado, Base):
    __tablename__ = "limite"

    gerente_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("usuario.id"), primary_key=True)
    por_pago: Mapped[Decimal | None]
    mensual: Mapped[Decimal | None]


class ConfiguracionIA(ConActualizado, Base):
    __tablename__ = "configuracion_ia"

    gerente_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("usuario.id"), primary_key=True)
    proveedor: Mapped[str] = mapped_column(server_default=text("'incluida'"))
    api_key_cifrada: Mapped[bytes | None] = mapped_column(LargeBinary)
    url_modelo: Mapped[str | None]
    respaldo_activo: Mapped[bool] = mapped_column(server_default=text("true"))
    estado: Mapped[str] = mapped_column(server_default=text("'sin_configurar'"))
    ultimo_error: Mapped[str | None]
    ultima_prueba_en: Mapped[datetime | None]
