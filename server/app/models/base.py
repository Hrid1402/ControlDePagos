import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, FetchedValue, MetaData, Numeric, Text, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

CONVENCION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=CONVENCION)
    type_annotation_map = {
        str: Text(),
        datetime: DateTime(timezone=True),
        Decimal: Numeric(12, 2),
    }


class ConId:
    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, server_default=text("uuid_generate_v7()")
    )


class ConCreado:
    creado_en: Mapped[datetime] = mapped_column(server_default=text("now()"))


class ConActualizado(ConCreado):
    actualizado_en: Mapped[datetime] = mapped_column(
        server_default=text("now()"), server_onupdate=FetchedValue()
    )
