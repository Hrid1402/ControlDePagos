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


def test_solicitud_aprobacion_persistencia_sql_orm_y_fks(
    db: Session,
    dos_gerentes: DosGerentes,
) -> None:
    """SolicitudAprobacion persiste coincidiendo SQL y ORM, y valida sus llaves foráneas."""
    from app.models import SolicitudAprobacion
    from tests.conftest import nueva_deuda

    gerente = dos_gerentes.uno.gerente
    asistente = dos_gerentes.uno.asistente
    deuda = nueva_deuda(db, gerente, monto="400.00")

    solicitud = SolicitudAprobacion(
        deuda_id=deuda.id,
        asistente_id=asistente.id,
        monto=Decimal("400.00"),
        motivo="Excede límite por pago",
    )
    db.add(solicitud)
    db.flush()

    # Comprobar SQL directo
    fila = db.execute(
        text(
            "SELECT id, deuda_id, asistente_id, monto, moneda, estado, "
            "recordatorios_enviados, motivo, creado_en FROM solicitud_aprobacion WHERE id = :id"
        ),
        {"id": solicitud.id},
    ).one()

    assert fila.id.version == 7
    assert fila.deuda_id == deuda.id
    assert fila.asistente_id == asistente.id
    assert fila.monto == Decimal("400.00")
    assert fila.moneda == "PEN"
    assert fila.estado == "pendiente"
    assert fila.recordatorios_enviados == 0
    assert fila.motivo == "Excede límite por pago"
    assert fila.creado_en is not None

    # Probar FK deuda_id
    with pytest.raises(IntegrityError, match="fk_solicitud_aprobacion_deuda_id_deuda"):
        with db.begin_nested():
            db.add(
                SolicitudAprobacion(
                    deuda_id=uuid.uuid4(),
                    asistente_id=asistente.id,
                    monto=Decimal("50.00"),
                )
            )
            db.flush()

    # Probar FK asistente_id (deuda distinta para no colisionar con uq pendiente)
    deuda_fk_asistente = nueva_deuda(db, gerente, monto="50.00")
    with pytest.raises(IntegrityError, match="fk_solicitud_aprobacion_asistente_id_usuario"):
        with db.begin_nested():
            db.add(
                SolicitudAprobacion(
                    deuda_id=deuda_fk_asistente.id,
                    asistente_id=uuid.uuid4(),
                    monto=Decimal("50.00"),
                )
            )
            db.flush()

    # Probar FK resuelta_por
    deuda_fk_resolutor = nueva_deuda(db, gerente, monto="50.00")
    with pytest.raises(IntegrityError, match="fk_solicitud_aprobacion_resuelta_por_usuario"):
        with db.begin_nested():
            db.add(
                SolicitudAprobacion(
                    deuda_id=deuda_fk_resolutor.id,
                    asistente_id=asistente.id,
                    monto=Decimal("50.00"),
                    resuelta_por=uuid.uuid4(),
                )
            )
            db.flush()


def test_solicitud_aprobacion_rechaza_monto_y_estado_invalidos(
    db: Session,
    dos_gerentes: DosGerentes,
) -> None:
    """Las restricciones CHECK rechazan monto <= 0 y estado fuera de catálogo."""
    from app.models import SolicitudAprobacion
    from tests.conftest import nueva_deuda

    gerente = dos_gerentes.uno.gerente
    asistente = dos_gerentes.uno.asistente
    deuda = nueva_deuda(db, gerente, monto="100.00")

    # monto = 0
    with pytest.raises(IntegrityError, match="ck_solicitud_aprobacion_monto"):
        with db.begin_nested():
            db.add(
                SolicitudAprobacion(
                    deuda_id=deuda.id,
                    asistente_id=asistente.id,
                    monto=Decimal("0"),
                )
            )
            db.flush()

    # monto negativo
    with pytest.raises(IntegrityError, match="ck_solicitud_aprobacion_monto"):
        with db.begin_nested():
            db.add(
                SolicitudAprobacion(
                    deuda_id=deuda.id,
                    asistente_id=asistente.id,
                    monto=Decimal("-5.00"),
                )
            )
            db.flush()

    # estado inválido
    with pytest.raises(IntegrityError, match="ck_solicitud_aprobacion_estado"):
        with db.begin_nested():
            db.add(
                SolicitudAprobacion(
                    deuda_id=deuda.id,
                    asistente_id=asistente.id,
                    monto=Decimal("50.00"),
                    estado="desconocido",
                )
            )
            db.flush()


def test_indice_parcial_uq_solicitud_aprobacion_pendiente(
    db: Session,
    dos_gerentes: DosGerentes,
) -> None:
    """uq_solicitud_aprobacion_pendiente impide dos pendientes y permite reintentos resueltos."""
    from app.models import SolicitudAprobacion
    from tests.conftest import nueva_deuda

    gerente = dos_gerentes.uno.gerente
    asistente = dos_gerentes.uno.asistente
    deuda = nueva_deuda(db, gerente, monto="350.00")

    # 1. Primera solicitud pendiente -> OK
    s1 = SolicitudAprobacion(
        deuda_id=deuda.id,
        asistente_id=asistente.id,
        monto=Decimal("350.00"),
        estado="pendiente",
    )
    db.add(s1)
    db.flush()

    # 2. Segunda solicitud pendiente en la misma deuda -> choca con uq
    s2 = SolicitudAprobacion(
        deuda_id=deuda.id,
        asistente_id=asistente.id,
        monto=Decimal("350.00"),
        estado="pendiente",
    )
    with pytest.raises(IntegrityError, match="uq_solicitud_aprobacion_pendiente"):
        with db.begin_nested():
            db.add(s2)
            db.flush()

    # 3. Resolver la primera solicitud a 'rechazada'
    s1.estado = "rechazada"
    s1.resuelta_por = gerente.id
    db.flush()

    # 4. Ahora sí se puede crear una nueva solicitud pendiente en la misma deuda
    s3 = SolicitudAprobacion(
        deuda_id=deuda.id,
        asistente_id=asistente.id,
        monto=Decimal("350.00"),
        estado="pendiente",
    )
    db.add(s3)
    db.flush()
    assert s3.id is not None

    # 5. Si la segunda se aprueba, ambas resueltas coexisten sin conflicto en el índice parcial
    s3.estado = "aprobada"
    s3.resuelta_por = gerente.id
    db.flush()


def test_aislamiento_solicitudes_ajenas_no_visibles(
    db: Session,
    dos_gerentes: DosGerentes,
) -> None:
    """solicitudes_de_gerente garantiza que ningún equipo vea solicitudes de otro gerente."""
    from app.models import SolicitudAprobacion
    from app.services.limites import solicitudes_de_gerente
    from tests.conftest import nueva_deuda

    g1, a1 = dos_gerentes.uno.gerente, dos_gerentes.uno.asistente
    g2, a2 = dos_gerentes.dos.gerente, dos_gerentes.dos.asistente

    d1 = nueva_deuda(db, g1, monto="100.00")
    d2 = nueva_deuda(db, g2, monto="200.00")

    sol1 = SolicitudAprobacion(
        deuda_id=d1.id, asistente_id=a1.id, monto=Decimal("100.00"), estado="pendiente"
    )
    sol2 = SolicitudAprobacion(
        deuda_id=d2.id, asistente_id=a2.id, monto=Decimal("200.00"), estado="pendiente"
    )
    db.add_all([sol1, sol2])
    db.flush()

    # Gerente 1 solo ve su solicitud
    solicitudes_g1 = solicitudes_de_gerente(db, g1.id)
    assert len(solicitudes_g1) == 1
    assert solicitudes_g1[0].id == sol1.id
    assert solicitudes_g1[0].deuda_id == d1.id

    # Gerente 2 solo ve su solicitud
    solicitudes_g2 = solicitudes_de_gerente(db, g2.id)
    assert len(solicitudes_g2) == 1
    assert solicitudes_g2[0].id == sol2.id
    assert solicitudes_g2[0].deuda_id == d2.id
