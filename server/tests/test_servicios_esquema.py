"""H10 en la base (TASK-32): unicidad de empresa y código, representación de la empresa y baja.

Se inserta directo en las tablas, sin pasar por la API, para probar que la base sola rechaza lo
que la API ya normaliza (migración 0006).
"""

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.dependencias import Origen
from app.models import Deuda, Recurrencia, Servicio, Usuario
from app.services.empresas import EMPRESAS_COMUNES, sincronizar_empresas
from app.services.servicios import dar_de_baja
from tests.conftest import DosGerentes, nueva_categoria

ORIGEN = Origen(dispositivo="pruebas", ip=None)
ENEL = next(e for e in EMPRESAS_COMUNES if e.nombre == "Enel")


def servicio(
    db: Session,
    gerente: Usuario,
    codigo: str = "AB-100",
    empresa_nombre: str | None = "Electro Oriente",
    empresa_id: uuid.UUID | None = None,
) -> Servicio:
    nuevo = Servicio(
        gerente_id=gerente.id,
        categoria_id=nueva_categoria(db, gerente).id,
        empresa_id=empresa_id,
        empresa_nombre=empresa_nombre,
        codigo_suministro=codigo,
        lugar_pago="agente_bcp",
    )
    with db.begin_nested():
        db.add(nuevo)
        db.flush()
    return nuevo


def rechaza(db: Session, restriccion: str, gerente: Usuario, **campos: Any) -> None:
    with pytest.raises(IntegrityError, match=restriccion):
        servicio(db, gerente, **campos)


# Unicidad (CA03)


def test_ca03_el_mismo_nombre_y_codigo_con_otras_mayusculas_es_duplicado(
    db: Session, dos_gerentes: DosGerentes
) -> None:
    gerente = dos_gerentes.uno.gerente
    servicio(db, gerente, codigo="AB-100", empresa_nombre="Electro Oriente")

    rechaza(
        db,
        "uq_servicio_codigo",
        gerente=gerente,
        codigo="ab-100",
        empresa_nombre="ELECTRO ORIENTE",
    )


def test_ca03_la_misma_empresa_del_catalogo_y_codigo_es_duplicado(
    db: Session, dos_gerentes: DosGerentes
) -> None:
    sincronizar_empresas(db)
    gerente = dos_gerentes.uno.gerente
    servicio(db, gerente, codigo="12345678", empresa_nombre=None, empresa_id=ENEL.id)

    rechaza(
        db,
        "uq_servicio_codigo",
        gerente=gerente,
        codigo="12345678",
        empresa_nombre=None,
        empresa_id=ENEL.id,
    )


def test_ca03_otro_codigo_u_otra_empresa_no_es_duplicado(
    db: Session, dos_gerentes: DosGerentes
) -> None:
    gerente = dos_gerentes.uno.gerente
    servicio(db, gerente, codigo="AB-100", empresa_nombre="Electro Oriente")

    servicio(db, gerente, codigo="AB-101", empresa_nombre="Electro Oriente")
    servicio(db, gerente, codigo="AB-100", empresa_nombre="Electro Sur Este")


def test_ca03_otro_gerente_puede_tener_la_misma_empresa_y_codigo(
    db: Session, dos_gerentes: DosGerentes
) -> None:
    servicio(db, dos_gerentes.uno.gerente, codigo="AB-100")

    otro = servicio(db, dos_gerentes.dos.gerente, codigo="AB-100")

    assert otro.gerente_id == dos_gerentes.dos.gerente.id


def test_ca03_un_servicio_eliminado_libera_el_codigo_y_uno_de_baja_no(
    db: Session, dos_gerentes: DosGerentes
) -> None:
    gerente = dos_gerentes.uno.gerente
    de_baja = servicio(db, gerente, codigo="AB-100")
    de_baja.estado = "baja"
    db.flush()
    rechaza(db, "uq_servicio_codigo", gerente=gerente, codigo="AB-100")

    de_baja.eliminado_en = datetime.now(UTC)
    db.flush()
    servicio(db, gerente, codigo="AB-100")


# Representación normalizada


@pytest.mark.parametrize("codigo", ["AB 100", " AB-100", "AB-100 ", "AB\t100", ""])
def test_el_codigo_no_admite_espacios_ni_vacio(
    db: Session, dos_gerentes: DosGerentes, codigo: str
) -> None:
    rechaza(db, "ck_servicio_codigo", gerente=dos_gerentes.uno.gerente, codigo=codigo)


@pytest.mark.parametrize(
    "nombre", ["Electro  Oriente", " Electro Oriente", "Electro Oriente ", "Electro\tOriente", ""]
)
def test_el_nombre_manual_no_admite_espacios_sobrantes(
    db: Session, dos_gerentes: DosGerentes, nombre: str
) -> None:
    rechaza(
        db, "ck_servicio_empresa_nombre", gerente=dos_gerentes.uno.gerente, empresa_nombre=nombre
    )


def test_ca01_la_empresa_es_del_catalogo_o_manual_pero_no_ambas_ni_ninguna(
    db: Session, dos_gerentes: DosGerentes
) -> None:
    sincronizar_empresas(db)
    gerente = dos_gerentes.uno.gerente

    rechaza(db, "ck_servicio_empresa", gerente=gerente, empresa_id=ENEL.id)
    rechaza(db, "ck_servicio_empresa", gerente=gerente, empresa_nombre=None)


@pytest.mark.parametrize("lugar", ["banca_movil", "otro"])
def test_ca05_lugar_de_pago_valido(db: Session, dos_gerentes: DosGerentes, lugar: str) -> None:
    nuevo = servicio(db, dos_gerentes.uno.gerente)
    nuevo.lugar_pago = lugar
    db.flush()


def test_ca05_lugar_de_pago_fuera_de_la_lista(db: Session, dos_gerentes: DosGerentes) -> None:
    nuevo = servicio(db, dos_gerentes.uno.gerente)
    nuevo.lugar_pago = "yape"
    with pytest.raises(IntegrityError, match="ck_servicio_lugar_pago"):
        db.flush()


# Baja lógica (CA08)


def test_ca08_la_baja_conserva_las_deudas_y_detiene_la_recurrencia(
    db: Session, dos_gerentes: DosGerentes
) -> None:
    gerente = dos_gerentes.uno.gerente
    luz = servicio(db, gerente)
    recurrencia = Recurrencia(servicio_id=luz.id, tipo="variable", dia_vencimiento=20)
    deuda = Deuda(
        gerente_id=gerente.id,
        servicio_id=luz.id,
        periodo=date(2026, 10, 1),
        monto=Decimal("80.00"),
        fecha_vencimiento=date(2026, 10, 20),
    )
    db.add_all([recurrencia, deuda])
    db.flush()

    baja = dar_de_baja(db, gerente, luz.id, ORIGEN)

    db.refresh(luz)
    db.refresh(recurrencia)
    db.refresh(deuda)
    assert (luz.estado, luz.eliminado_en) == ("baja", None)
    assert recurrencia.activa is False
    assert (deuda.estado, deuda.monto) == ("pendiente", Decimal("80.00"))
    assert (baja.recurrencias_desactivadas, baja.deudas_pendientes) == (1, 1)
