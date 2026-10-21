"""Reglas documentales del comprobante (H24 CA04 y CA05, TASK-87).

evaluar no usa la base: cada prueba arma los datos extraídos y el reparto.
"""

import uuid
from dataclasses import replace
from datetime import date, datetime
from decimal import Decimal

import pytest

from app.core.tiempo import zona_horaria
from app.ocr.extraccion import Campo, DatosComprobante, Entidad
from app.services.reglas_comprobante import DeudaReparto, evaluar, misma_empresa

LIMA = zona_horaria()
SUBIDO = datetime(2026, 10, 20, 12, 0, tzinfo=LIMA)


def datos(
    monto: str = "85.40",
    moneda: str = "PEN",
    codigo: str = "12345678",
    empresa: str = "HIDRANDINA S.A.",
    fecha: datetime = datetime(2026, 10, 20, 10, 35, tzinfo=LIMA),
    confianza: float = 0.97,
) -> DatosComprobante:
    return DatosComprobante(
        entidad=Entidad.BCP,
        numero_operacion=Campo("00456789", confianza),
        monto=Campo(Decimal(monto), confianza),
        moneda=Campo(moneda, confianza),
        fecha_pago=Campo(fecha, confianza),
        empresa=Campo(empresa, confianza),
        codigo=Campo(codigo, confianza),
    )


def deuda(
    aplicado: str = "85.40",
    codigo: str = "1234-5678",
    empresas: tuple[str, ...] = ("Hidrandina",),
    desde: date = date(2026, 10, 1),
) -> DeudaReparto:
    return DeudaReparto(
        id=uuid.uuid4(),
        moneda="PEN",
        codigo=codigo,
        empresas=list(empresas),
        desde=desde,
        monto_aplicado=Decimal(aplicado),
    )


def test_datos_que_coinciden_validan_por_lo_aplicado() -> None:
    reparto = deuda()

    decision = evaluar(datos(), "PEN", [reparto], SUBIDO)

    assert (decision.estado, decision.motivo) == ("validado", None)
    assert decision.aplicados == {reparto.id: Decimal("85.40")}


@pytest.mark.parametrize("monto", ["85.30", "85.50"])
def test_la_tolerancia_es_de_diez_centimos(monto: str) -> None:
    assert evaluar(datos(monto=monto), "PEN", [deuda()], SUBIDO).estado == "validado"


def test_un_monto_menor_valida_un_pago_parcial() -> None:
    reparto = deuda()

    decision = evaluar(datos(monto="50.00"), "PEN", [reparto], SUBIDO)

    assert (decision.estado, decision.motivo) == ("validado", "monto_menor")
    assert decision.aplicados == {reparto.id: Decimal("50.00")}
    assert "Pago parcial de PEN 50.00" in decision.observacion


def test_un_monto_mayor_va_a_revision_sin_aplicar_el_excedente() -> None:
    decision = evaluar(datos(monto="85.51"), "PEN", [deuda()], SUBIDO)

    assert (decision.estado, decision.motivo, decision.aplicados) == (
        "en_revision",
        "monto_mayor",
        {},
    )


def test_un_comprobante_para_varias_deudas_valida_el_reparto_completo() -> None:
    luz = deuda("60.00")
    agua = deuda("25.40", codigo="99887766", empresas=("Sedalib",))

    decision = evaluar(datos(), "PEN", [luz, agua], SUBIDO)

    assert decision.estado == "validado"
    assert decision.aplicados == {luz.id: Decimal("60.00"), agua.id: Decimal("25.40")}


def test_varias_deudas_con_monto_menor_las_reparte_el_gerente() -> None:
    decision = evaluar(datos(monto="70.00"), "PEN", [deuda("60.00"), deuda("25.40")], SUBIDO)

    assert (decision.estado, decision.motivo) == ("en_revision", "monto_menor")


def test_un_codigo_de_otra_deuda_se_rechaza() -> None:
    decision = evaluar(datos(codigo="55554444"), "PEN", [deuda()], SUBIDO)

    assert (decision.estado, decision.motivo) == ("rechazado", "otra_deuda")


def test_la_empresa_distinta_con_el_codigo_correcto_va_a_revision() -> None:
    decision = evaluar(datos(empresa="LUZ DEL SUR"), "PEN", [deuda()], SUBIDO)

    assert (decision.estado, decision.motivo) == ("en_revision", None)
    assert "LUZ DEL SUR" in decision.observacion


def test_una_moneda_distinta_va_a_revision_sin_convertir() -> None:
    decision = evaluar(datos(moneda="USD"), "PEN", [deuda()], SUBIDO)

    assert decision.estado == "en_revision"
    assert "USD" in decision.observacion and "PEN" in decision.observacion


@pytest.mark.parametrize(
    "fecha",
    [
        datetime(2026, 9, 30, 23, 0, tzinfo=LIMA),  # antes del periodo de la deuda
        datetime(2026, 10, 20, 12, 1, tzinfo=LIMA),  # después de subir el comprobante
    ],
)
def test_una_fecha_dudosa_va_a_revision(fecha: datetime) -> None:
    decision = evaluar(datos(fecha=fecha), "PEN", [deuda()], SUBIDO)

    assert (decision.estado, decision.motivo) == ("en_revision", "fecha_dudosa")


def test_la_emision_de_la_deuda_limita_la_fecha_de_pago() -> None:
    emitida = deuda(desde=date(2026, 10, 21))

    decision = evaluar(datos(), "PEN", [emitida], datetime(2026, 10, 22, tzinfo=LIMA))

    assert decision.motivo == "fecha_dudosa"


@pytest.mark.parametrize("confianza", [0.79, 0.65])
def test_un_campo_leido_con_duda_va_a_revision(confianza: float) -> None:
    dudoso = replace(datos(), monto=Campo(Decimal("85.40"), confianza))

    decision = evaluar(dudoso, "PEN", [deuda()], SUBIDO)

    assert (decision.estado, decision.motivo) == ("en_revision", "baja_confianza")


def test_la_baja_confianza_se_evalua_antes_que_el_monto() -> None:
    decision = evaluar(datos(monto="10.00", confianza=0.7), "PEN", [deuda()], SUBIDO)

    assert decision.motivo == "baja_confianza"


@pytest.mark.parametrize(
    ("leida", "empresas", "coincide"),
    [
        ("HIDRANDINA S.A.", ["Hidrandina"], True),
        ("ENEL DISTRIBUCION", ["Enel Distribución Perú S.A.A."], True),
        ("SEDALIB", ["", "Agua casa"], False),
        ("LUZ DEL SUR", ["Hidrandina"], False),
    ],
)
def test_compara_la_empresa_por_similitud(leida: str, empresas: list[str], coincide: bool) -> None:
    assert misma_empresa(leida, empresas) is coincide
