import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import ForeignKey, Index, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, ConActualizado, ConCreado, ConId


class Ubigeo(ConCreado, Base):
    __tablename__ = "ubigeo"

    codigo: Mapped[str] = mapped_column(primary_key=True)
    departamento: Mapped[str]
    provincia: Mapped[str]
    distrito: Mapped[str]


class Inmueble(ConId, ConActualizado, Base):
    __tablename__ = "inmueble"
    __table_args__ = (
        Index(
            "uq_inmueble_nombre",
            "gerente_id",
            text("lower(nombre)"),
            unique=True,
            postgresql_where=text("eliminado_en IS NULL"),
        ),
    )

    gerente_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("usuario.id"), index=True)
    nombre: Mapped[str]
    ubigeo: Mapped[str] = mapped_column(ForeignKey("ubigeo.codigo"), index=True)
    direccion: Mapped[str | None]
    eliminado_en: Mapped[datetime | None]


class Empresa(ConId, ConActualizado, Base):
    __tablename__ = "empresa"
    __table_args__ = (UniqueConstraint("ruc"),)

    nombre: Mapped[str]
    ruc: Mapped[str | None]
    tipo_servicio: Mapped[str]
    patron_codigo: Mapped[str | None]
    url_portal: Mapped[str | None]
    tiene_robot: Mapped[bool] = mapped_column(server_default=text("false"))
    robot_activo: Mapped[bool] = mapped_column(server_default=text("false"))


class EmpresaZona(ConCreado, Base):
    __tablename__ = "empresa_zona"

    empresa_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("empresa.id", ondelete="CASCADE"), primary_key=True
    )
    ubigeo: Mapped[str] = mapped_column(ForeignKey("ubigeo.codigo"), primary_key=True, index=True)


class CanalPago(ConId, ConActualizado, Base):
    __tablename__ = "canal_pago"
    __table_args__ = (UniqueConstraint("empresa_id", "lugar_pago"),)

    empresa_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("empresa.id", ondelete="CASCADE"))
    lugar_pago: Mapped[str]
    comision: Mapped[Decimal] = mapped_column(server_default=text("0"))
