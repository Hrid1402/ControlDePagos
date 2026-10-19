import uuid
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models import Categoria, Deuda, Servicio, Usuario


def crear_gerente(db: Session) -> Usuario:
    gerente = Usuario(rol="gerente", username="gerente1", password_hash="x")
    db.add(gerente)
    db.flush()
    return gerente


def crear_asistente(db: Session, gerente: Usuario, username: str) -> Usuario:
    asistente = Usuario(
        rol="asistente", gerente_id=gerente.id, username=username, password_hash="x"
    )
    db.add(asistente)
    db.flush()
    return asistente


def test_existen_las_37_tablas(db: Session) -> None:
    total = db.execute(
        text(
            "SELECT count(*) FROM information_schema.tables "
            "WHERE table_schema = 'public' AND table_name <> 'alembic_version'"
        )
    ).scalar_one()
    assert total == 37


def test_uuid_v7_ordenado(db: Session) -> None:
    primero = db.execute(text("SELECT uuid_generate_v7()")).scalar_one()
    segundo = db.execute(text("SELECT uuid_generate_v7()")).scalar_one()
    assert uuid.UUID(str(primero)).version == 7
    assert str(primero) < str(segundo)


def test_la_base_pone_los_valores_por_defecto(db: Session) -> None:
    gerente = crear_gerente(db)
    db.refresh(gerente)
    assert gerente.id.version == 7
    assert gerente.estado == "activa"
    assert gerente.contrasena_inicial is True
    assert gerente.horas_recordatorio == 4
    assert gerente.creado_en is not None


def test_una_sola_asistente_activa_por_gerente(db: Session) -> None:
    gerente = crear_gerente(db)
    crear_asistente(db, gerente, "asistente1")
    with pytest.raises(IntegrityError, match="uq_usuario_asistente_activa"):
        crear_asistente(db, gerente, "asistente2")


def test_username_unico_sin_distinguir_mayusculas(db: Session) -> None:
    gerente = crear_gerente(db)
    crear_asistente(db, gerente, "maria")
    gerente.estado = "inactiva"
    with pytest.raises(IntegrityError, match="uq_usuario_username"):
        db.add(Usuario(rol="gerente", username="MARIA", password_hash="x"))
        db.flush()


def test_la_deuda_rechaza_monto_cero(db: Session) -> None:
    gerente = crear_gerente(db)
    categoria = Categoria(gerente_id=gerente.id, nombre="Luz", tipo="servicio_variable")
    db.add(categoria)
    db.flush()
    servicio = Servicio(
        gerente_id=gerente.id,
        categoria_id=categoria.id,
        empresa_nombre="Hidrandina",
        codigo_suministro="123456",
    )
    db.add(servicio)
    db.flush()
    with pytest.raises(IntegrityError, match="ck_deuda_monto"):
        db.add(
            Deuda(
                gerente_id=gerente.id,
                servicio_id=servicio.id,
                periodo=date(2026, 10, 1),
                monto=Decimal("0"),
                fecha_vencimiento=date(2026, 10, 20),
            )
        )
        db.flush()


def test_get_db_entrega_una_sesion() -> None:
    generador = get_db()
    sesion = next(generador)
    assert isinstance(sesion, Session)
    generador.close()
