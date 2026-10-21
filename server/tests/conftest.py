import hashlib
import io
import os
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from alembic import command
from alembic.config import Config
from botocore.exceptions import ClientError
from celery.canvas import Signature
from sqlalchemy.orm import Session

os.environ["DATABASE_URL"] = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+psycopg://postgres:postgres@localhost:5432/control_pagos_test",
)
# Las pruebas no dependen de la clave del .env de cada desarrollador.
os.environ.setdefault("JWT_SECRET", "clave-de-pruebas-clave-de-pruebas")

from app.core import eventos  # noqa: E402
from app.core.eventos import Evento  # noqa: E402
from app.models import (  # noqa: E402
    Categoria,
    Comprobante,
    ComprobanteDeuda,
    Deuda,
    OrdenPago,
    Servicio,
    Usuario,
)
from app.services import archivos  # noqa: E402
from app.workers import encolar as modulo_encolar  # noqa: E402


@dataclass
class Equipo:
    gerente: Usuario
    asistente: Usuario


@dataclass
class DosGerentes:
    uno: Equipo
    dos: Equipo


@pytest.fixture(scope="session", autouse=True)
def esquema() -> None:
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    command.upgrade(config, "head")


@pytest.fixture
def db() -> Iterator[Session]:
    from app.core.database import engine

    with engine.connect() as conexion:
        transaccion = conexion.begin()
        sesion = Session(bind=conexion, join_transaction_mode="create_savepoint")
        yield sesion
        sesion.close()
        transaccion.rollback()


def crear_equipo(db: Session, sufijo: str) -> Equipo:
    gerente = Usuario(rol="gerente", username=f"gerente_{sufijo}", password_hash="x")
    db.add(gerente)
    db.flush()
    asistente = Usuario(
        rol="asistente", gerente_id=gerente.id, username=f"asistente_{sufijo}", password_hash="x"
    )
    db.add(asistente)
    db.flush()
    db.refresh(gerente)
    db.refresh(asistente)
    return Equipo(gerente=gerente, asistente=asistente)


@pytest.fixture
def dos_gerentes(db: Session) -> DosGerentes:
    """Dos gerentes, cada uno con su asistente activa, para probar el aislamiento."""
    return DosGerentes(uno=crear_equipo(db, "uno"), dos=crear_equipo(db, "dos"))


@pytest.fixture
def publicados(monkeypatch: pytest.MonkeyPatch) -> list[tuple[uuid.UUID, Evento]]:
    """Captura los eventos que salen tras el commit en lugar de enviarlos a Redis."""
    salida: list[tuple[uuid.UUID, Evento]] = []

    def capturar(usuario_id: uuid.UUID, evento: Evento) -> bool:
        salida.append((usuario_id, evento))
        return True

    monkeypatch.setattr(eventos, "publicar", capturar)
    return salida


@pytest.fixture
def enviadas(monkeypatch: pytest.MonkeyPatch) -> list[Signature]:
    """Captura las tareas que se encolan tras el commit en lugar de enviarlas a Redis, donde las
    tomaría el worker local."""
    salida: list[Signature] = []

    def capturar(firma: Signature) -> bool:
        salida.append(firma)
        return True

    monkeypatch.setattr(modulo_encolar, "encolar", capturar)
    return salida


def nueva_categoria(db: Session, gerente: Usuario, tipo: str = "servicio_variable") -> Categoria:
    categoria = Categoria(gerente_id=gerente.id, nombre=f"Cat {uuid.uuid4().hex}", tipo=tipo)
    db.add(categoria)
    db.flush()
    return categoria


def nueva_deuda(
    db: Session,
    gerente: Usuario,
    monto: str | None = "100.00",
    moneda: str = "PEN",
    estado: str = "pendiente",
    fecha_vencimiento: date = date(2026, 10, 25),
    tipo_categoria: str = "servicio_variable",
    categoria: Categoria | None = None,
) -> Deuda:
    """Deuda con su propio servicio y, si no se indica, su propia categoría, para no chocar con
    las unicidades por gerente."""
    marca = uuid.uuid4().hex
    if categoria is None:
        categoria = nueva_categoria(db, gerente, tipo_categoria)
    servicio = Servicio(
        gerente_id=gerente.id,
        categoria_id=categoria.id,
        empresa_nombre="Hidrandina",
        codigo_suministro=marca,
    )
    db.add(servicio)
    db.flush()
    deuda = Deuda(
        gerente_id=gerente.id,
        servicio_id=servicio.id,
        periodo=fecha_vencimiento.replace(day=1),
        monto=None if monto is None else Decimal(monto),
        moneda=moneda,
        estado=estado,
        fecha_vencimiento=fecha_vencimiento,
    )
    db.add(deuda)
    db.flush()
    return deuda


def nuevo_comprobante(
    db: Session,
    deuda: Deuda,
    subido_por: Usuario,
    monto_aplicado: str,
    estado: str = "validado",
    creado_en: datetime | None = None,
) -> Comprobante:
    """Comprobante con su abono a la deuda (comprobante_deuda)."""
    comprobante = Comprobante(
        gerente_id=deuda.gerente_id,
        archivo_url=f"comprobantes/{uuid.uuid4()}.jpg",
        archivo_tipo="jpg",
        archivo_bytes=1000,
        hash_sha256=hashlib.sha256(uuid.uuid4().bytes).hexdigest(),
        monto=Decimal(monto_aplicado),
        moneda=deuda.moneda,
        estado=estado,
        subido_por=subido_por.id,
    )
    if creado_en is not None:
        comprobante.creado_en = creado_en
    db.add(comprobante)
    db.flush()
    db.add(
        ComprobanteDeuda(
            comprobante_id=comprobante.id,
            deuda_id=deuda.id,
            monto_aplicado=Decimal(monto_aplicado),
        )
    )
    db.flush()
    return comprobante


def nueva_orden(
    db: Session,
    deuda: Deuda,
    estado: str = "enviada",
    plazo: datetime | None = None,
    asistente: Usuario | None = None,
    monto: str | None = None,
) -> OrdenPago:
    """Orden urgente del gerente de la deuda. Sin monto autoriza el monto y la moneda de la
    deuda, como hace TASK-63 al crearla sin abonos."""
    orden = OrdenPago(
        deuda_id=deuda.id,
        gerente_id=deuda.gerente_id,
        asistente_id=asistente.id if asistente else None,
        estado=estado,
        plazo=plazo,
        monto=Decimal(monto) if monto is not None else deuda.monto,
        moneda=deuda.moneda,
    )
    db.add(orden)
    db.flush()
    return orden


class S3EnMemoria:
    """Cliente S3 mínimo: guarda los objetos en un diccionario y puede fallar a pedido."""

    def __init__(self) -> None:
        self.objetos: dict[str, tuple[bytes, str]] = {}
        self.falla = False

    def _quizas_fallar(self, operacion: str) -> None:
        if self.falla:
            raise ClientError({"Error": {"Code": "500", "Message": "caído"}}, operacion)

    def put_object(self, Bucket: str, Key: str, Body: bytes, ContentType: str) -> None:
        self._quizas_fallar("PutObject")
        self.objetos[Key] = (Body, ContentType)

    def get_object(self, Bucket: str, Key: str) -> dict[str, Any]:
        self._quizas_fallar("GetObject")
        return {"Body": io.BytesIO(self.objetos[Key][0])}

    def delete_object(self, Bucket: str, Key: str) -> None:
        self._quizas_fallar("DeleteObject")
        self.objetos.pop(Key, None)

    def generate_presigned_url(self, operacion: str, Params: dict[str, str], ExpiresIn: int) -> str:
        self._quizas_fallar("GeneratePresignedUrl")
        return f"https://s3.local/{Params['Key']}?expira={ExpiresIn}"


@pytest.fixture
def s3(monkeypatch: pytest.MonkeyPatch) -> S3EnMemoria:
    cliente = S3EnMemoria()
    monkeypatch.setattr(archivos, "cliente_s3", lambda: cliente)
    return cliente
