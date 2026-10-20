"""Verificación del esquema existente para límites y solicitudes (H05, TASK-22).

Comprueba persistencia ORM/SQL, llaves foráneas, importes opcionales y restricciones CHECK.
"""

import uuid
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errores import ErrorApi
from app.models import Limite
from app.services.limites import fijar_limite, obtener_limite
from tests.conftest import DosGerentes


def test_limite_persistencia_sql_orm(db: Session, dos_gerentes: DosGerentes) -> None:
    """La persistencia de Limite coincide exactamente entre el ORM y la tabla SQL."""
    gerente = dos_gerentes.uno.gerente
    limite = Limite(
        gerente_id=gerente.id,
        por_pago=Decimal("150.50"),
        mensual=Decimal("1200.00"),
    )
    db.add(limite)
    db.flush()

    # Consulta directa SQL para validar tipos y persistencia real en la base
    fila = db.execute(
        text(
            "SELECT por_pago, mensual, creado_en, actualizado_en FROM limite WHERE gerente_id = :id"
        ),
        {"id": gerente.id},
    ).one()

    assert fila.por_pago == Decimal("150.50")
    assert fila.mensual == Decimal("1200.00")
    assert fila.creado_en is not None
    assert fila.actualizado_en is not None

    # Consulta a través del ORM y servicio
    recuperado = obtener_limite(db, gerente.id)
    assert recuperado is not None
    assert recuperado.por_pago == Decimal("150.50")
    assert recuperado.mensual == Decimal("1200.00")


def test_limite_rechaza_fk_gerente_inexistente(db: Session) -> None:
    """La llave foránea fk_limite_gerente_id_usuario rechaza un usuario inexistente."""
    id_inexistente = uuid.uuid4()
    limite = Limite(gerente_id=id_inexistente, por_pago=Decimal("50.00"))
    db.add(limite)
    with pytest.raises(IntegrityError, match="fk_limite_gerente_id_usuario"):
        db.flush()


@pytest.mark.parametrize(
    ("por_pago", "mensual"),
    [
        (None, None),
        (Decimal("100.00"), None),
        (None, Decimal("500.00")),
        (Decimal("100.00"), Decimal("500.00")),
        (Decimal("300.00"), Decimal("300.00")),
    ],
)
def test_limite_importes_opcionales(
    db: Session,
    dos_gerentes: DosGerentes,
    por_pago: Decimal | None,
    mensual: Decimal | None,
) -> None:
    """Los importes de límite son opcionales y admiten cualquier combinación válida."""
    gerente = dos_gerentes.uno.gerente
    limite = Limite(gerente_id=gerente.id, por_pago=por_pago, mensual=mensual)
    db.add(limite)
    db.flush()

    db.refresh(limite)
    assert limite.por_pago == por_pago
    assert limite.mensual == mensual


@pytest.mark.parametrize("monto_invalido", [Decimal("0"), Decimal("-15.00")])
def test_limite_rechaza_por_pago_menor_o_igual_a_cero(
    db: Session,
    dos_gerentes: DosGerentes,
    monto_invalido: Decimal,
) -> None:
    """La restricción ck_limite_por_pago rechaza montos cero o negativos."""
    gerente = dos_gerentes.uno.gerente
    limite = Limite(gerente_id=gerente.id, por_pago=monto_invalido)
    db.add(limite)
    with pytest.raises(IntegrityError, match="ck_limite_por_pago"):
        db.flush()


@pytest.mark.parametrize("monto_invalido", [Decimal("0"), Decimal("-50.00")])
def test_limite_rechaza_mensual_menor_o_igual_a_cero(
    db: Session,
    dos_gerentes: DosGerentes,
    monto_invalido: Decimal,
) -> None:
    """La restricción ck_limite_mensual rechaza montos cero o negativos."""
    gerente = dos_gerentes.uno.gerente
    limite = Limite(gerente_id=gerente.id, mensual=monto_invalido)
    db.add(limite)
    with pytest.raises(IntegrityError, match="ck_limite_mensual"):
        db.flush()


def test_limite_rechaza_por_pago_mayor_que_mensual(
    db: Session,
    dos_gerentes: DosGerentes,
) -> None:
    """La restricción ck_limite_por_pago_mensual rechaza por_pago mayor que mensual."""
    gerente = dos_gerentes.uno.gerente
    limite = Limite(
        gerente_id=gerente.id,
        por_pago=Decimal("800.00"),
        mensual=Decimal("500.00"),
    )
    db.add(limite)
    with pytest.raises(IntegrityError, match="ck_limite_por_pago_mensual"):
        db.flush()


def test_servicio_fijar_limite_valida_reglas_de_negocio(
    db: Session,
    dos_gerentes: DosGerentes,
) -> None:
    """fijar_limite rechaza valores inválidos con ErrorApi 400 antes de llegar a la BD."""
    gerente = dos_gerentes.uno.gerente

    # por_pago <= 0
    with pytest.raises(ErrorApi) as err1:
        fijar_limite(db, gerente.id, Decimal("0"), None)
    assert err1.value.status_code == 400
    assert err1.value.code == "MONTO_INVALIDO"

    # mensual <= 0
    with pytest.raises(ErrorApi) as err2:
        fijar_limite(db, gerente.id, None, Decimal("-10.00"))
    assert err2.value.status_code == 400
    assert err2.value.code == "MONTO_INVALIDO"

    # por_pago > mensual
    with pytest.raises(ErrorApi) as err3:
        fijar_limite(db, gerente.id, Decimal("600.00"), Decimal("400.00"))
    assert err3.value.status_code == 400
    assert err3.value.code == "LIMITE_INVALIDO"

    # Éxito
    guardado = fijar_limite(db, gerente.id, Decimal("200.00"), Decimal("500.00"))
    assert guardado.por_pago == Decimal("200.00")
    assert guardado.mensual == Decimal("500.00")
