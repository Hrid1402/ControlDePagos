import uuid
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models import Categoria, Deuda, Servicio, SolicitudAprobacion, Usuario
from tests.conftest import nueva_deuda


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


def generar_uuid_v7(db: Session) -> uuid.UUID:
    return uuid.UUID(str(db.execute(text("SELECT uuid_generate_v7()")).scalar_one()))


def test_uuid_v7_ordenado(db: Session) -> None:
    # UUID v7 solo garantiza orden entre milisegundos distintos: dentro del mismo milisegundo
    # el resto es aleatorio, así que se compara solo la marca de tiempo (48 bits, 12 hex).
    primero = generar_uuid_v7(db)
    segundo = generar_uuid_v7(db)
    assert primero.version == 7
    assert segundo.version == 7
    assert primero.hex[:12] <= segundo.hex[:12]


def test_uuid_v7_de_milisegundos_distintos_queda_ordenado(db: Session) -> None:
    primero = generar_uuid_v7(db)
    db.execute(text("SELECT pg_sleep(0.002)"))
    segundo = generar_uuid_v7(db)
    assert segundo > primero


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


ESTADOS_DEUDA = (
    "esperando_recibo",
    "pendiente",
    "esperando_aprobacion",
    "en_proceso",
    "por_validar",
    "pagada_parcial",
    "pagada",
    "con_problema",
    "anulada",
)
ESTADOS_SIN_MONTO = ("esperando_recibo", "anulada")


@pytest.mark.parametrize("estado", ESTADOS_SIN_MONTO)
def test_la_deuda_sin_importe_solo_existe_esperando_recibo_o_anulada(
    db: Session, estado: str
) -> None:
    deuda = nueva_deuda(db, crear_gerente(db), monto=None, estado=estado)
    db.refresh(deuda)
    assert deuda.monto is None


@pytest.mark.parametrize("estado", [e for e in ESTADOS_DEUDA if e not in ESTADOS_SIN_MONTO])
def test_la_deuda_operativa_exige_monto(db: Session, estado: str) -> None:
    with pytest.raises(IntegrityError, match="ck_deuda_monto"):
        nueva_deuda(db, crear_gerente(db), monto=None, estado=estado)


@pytest.mark.parametrize("estado", ESTADOS_DEUDA)
@pytest.mark.parametrize("monto", ["0", "-5.00"])
def test_ningun_estado_acepta_monto_cero_ni_negativo(db: Session, estado: str, monto: str) -> None:
    with pytest.raises(IntegrityError, match="ck_deuda_monto"):
        nueva_deuda(db, crear_gerente(db), monto=monto, estado=estado)


def test_esperando_recibo_y_anulada_aceptan_un_monto_positivo(db: Session) -> None:
    gerente = crear_gerente(db)
    for estado in ESTADOS_SIN_MONTO:
        assert nueva_deuda(db, gerente, monto="80.00", estado=estado).monto == Decimal("80.00")


def test_una_deuda_anulada_sin_monto_permite_registrar_otra_del_mismo_periodo(
    db: Session,
) -> None:
    gerente = crear_gerente(db)
    anulada = nueva_deuda(db, gerente, monto=None, estado="anulada")
    db.add(
        Deuda(
            gerente_id=gerente.id,
            servicio_id=anulada.servicio_id,
            periodo=anulada.periodo,
            monto=Decimal("90.00"),
            fecha_vencimiento=anulada.fecha_vencimiento,
        )
    )
    db.flush()
    # Con la anulada fuera del índice, una segunda deuda activa sí choca.
    with pytest.raises(IntegrityError, match="uq_deuda_periodo"):
        db.add(
            Deuda(
                gerente_id=gerente.id,
                servicio_id=anulada.servicio_id,
                periodo=anulada.periodo,
                monto=None,
                estado="esperando_recibo",
                fecha_vencimiento=anulada.fecha_vencimiento,
            )
        )
        db.flush()


def test_la_solicitud_de_aprobacion_guarda_la_moneda(db: Session) -> None:
    gerente = crear_gerente(db)
    asistente = crear_asistente(db, gerente, "asistente1")
    deuda = nueva_deuda(db, gerente, moneda="USD")
    solicitud = SolicitudAprobacion(deuda_id=deuda.id, asistente_id=asistente.id, monto=Decimal(5))
    db.add(solicitud)
    db.flush()
    db.refresh(solicitud)
    assert solicitud.moneda == "PEN"
    with pytest.raises(IntegrityError, match="ck_solicitud_aprobacion_moneda"):
        solicitud.moneda = "EUR"
        db.flush()


def test_get_db_entrega_una_sesion() -> None:
    generador = get_db()
    sesion = next(generador)
    assert isinstance(sesion, Session)
    generador.close()
