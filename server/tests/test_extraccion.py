"""Extracción de datos por entidad (H24 CA03 y CA04, TASK-86).

Cada ejemplo del banco (tests/ejemplos_comprobantes.py) se extrae y se compara con lo esperado.
La última prueba lee con PaddleOCR una constancia dibujada y extrae sus campos: solo corre con el
grupo ocr instalado.
"""

from decimal import Decimal

import pytest

from app.ocr.extraccion import (
    CampoClave,
    Entidad,
    a_decimal,
    detectar_entidad,
    extraer,
    normalizar,
)
from app.ocr.motor import LecturaOcr, Linea
from tests.ejemplos_comprobantes import EJEMPLOS, Ejemplo, lima


@pytest.mark.parametrize("ejemplo", EJEMPLOS, ids=lambda e: e.nombre)
def test_extrae_los_campos_de_cada_formato(ejemplo: Ejemplo) -> None:
    datos = extraer(ejemplo.lectura())

    for campo, esperado in ejemplo.esperado.items():
        if campo == "entidad":
            assert datos.entidad.value == esperado
        elif campo == "faltantes":
            assert [f.value for f in datos.faltantes] == esperado
        else:
            obtenido = getattr(datos, campo)
            assert (obtenido.valor if obtenido else None) == esperado, campo


@pytest.mark.parametrize(
    "ejemplo", [e for e in EJEMPLOS if len(e.esperado) == 7], ids=lambda e: e.nombre
)
def test_un_formato_completo_no_tiene_campos_faltantes(ejemplo: Ejemplo) -> None:
    assert extraer(ejemplo.lectura()).faltantes == []


def test_cada_entidad_admitida_tiene_un_ejemplo_completo() -> None:
    completas = {e.esperado["entidad"] for e in EJEMPLOS if len(e.esperado) == 7}

    assert completas == {e.value for e in Entidad if e is not Entidad.OTRA}


@pytest.mark.parametrize(
    ("texto", "entidad"),
    [
        ("AGENTE BCP\nBCP", Entidad.AGENTE_BCP),
        ("¡Yapeaste!\nBanco de Crédito BCP", Entidad.YAPE),
        ("Banco de Credito del Peru", Entidad.BCP),
        ("Kas Net", Entidad.KASNET),
        ("Scotiabank Perú", Entidad.SCOTIABANK),
        ("Pago con tarjeta", Entidad.OTRA),
    ],
)
def test_detecta_la_entidad_por_palabras_clave(texto: str, entidad: Entidad) -> None:
    lineas = [Linea(normalizar(t), 0.9) for t in texto.split("\n")]

    assert detectar_entidad(lineas) == entidad


@pytest.mark.parametrize(
    ("numero", "monto"),
    [
        ("85.40", Decimal("85.40")),
        ("85,40", Decimal("85.40")),
        ("1,234.50", Decimal("1234.50")),
        ("1 234.50", Decimal("1234.50")),
        ("1,234", Decimal("1234.00")),
        ("35", Decimal("35.00")),
        ("0.00", None),
    ],
)
def test_convierte_importes_con_coma_o_punto(numero: str, monto: Decimal | None) -> None:
    assert a_decimal(numero) == monto


def test_cada_campo_lleva_la_menor_confianza_de_sus_lineas() -> None:
    lectura = LecturaOcr(
        [
            Linea("BCP", 0.99),
            Linea("Monto pagado", 0.95),
            Linea("S/ 85.40", 0.72),
            Linea("Empresa: HIDRANDINA", 0.97),
        ],
        paginas=1,
    )

    datos = extraer(lectura)

    assert datos.monto is not None and datos.monto.confianza == pytest.approx(0.72)
    assert datos.empresa is not None and datos.empresa.confianza == pytest.approx(0.97)


def test_sin_texto_no_extrae_nada() -> None:
    datos = extraer(LecturaOcr([], paginas=1))

    assert datos.entidad == Entidad.OTRA
    assert datos.faltantes == list(CampoClave)


def test_una_fecha_imposible_no_se_inventa() -> None:
    datos = extraer(LecturaOcr([Linea("BCP", 0.9), Linea("Fecha: 31/02/2026", 0.9)], paginas=1))

    assert datos.fecha_pago is None


def test_la_fecha_sin_hora_queda_a_medianoche_de_lima() -> None:
    datos = extraer(LecturaOcr([Linea("Interbank", 0.9), Linea("Fecha: 18/10/2026", 0.9)], 1))

    assert datos.fecha_pago is not None and datos.fecha_pago.valor == lima(2026, 10, 18)


def test_el_json_guarda_valores_como_texto_y_los_faltantes() -> None:
    (bcp,) = [e for e in EJEMPLOS if e.nombre == "bcp_app"]

    datos = extraer(bcp.lectura()).a_json()

    assert datos["entidad"] == "bcp"
    assert datos["campos"]["monto"] == {"valor": "85.40", "confianza": 0.98}
    assert datos["campos"]["fecha_pago"]["valor"] == "2026-10-20T10:35:00-05:00"
    assert datos["faltantes"] == []


def test_paddleocr_y_la_extraccion_juntos_leen_una_constancia() -> None:
    pytest.importorskip("paddleocr")
    from app.ocr.motor import leer_documento
    from tests.test_ocr_motor import comprobante_sintetico

    datos = extraer(leer_documento(comprobante_sintetico(), "png"))

    assert datos.entidad == Entidad.BCP
    assert datos.empresa is not None and datos.empresa.valor == "HIDRANDINA"
    assert datos.codigo is not None and datos.codigo.valor == "12345678"
    assert datos.monto is not None and datos.monto.valor == Decimal("85.40")
    assert datos.numero_operacion is not None and datos.numero_operacion.valor == "00456789"
    assert datos.fecha_pago is not None and datos.fecha_pago.valor == lima(2026, 10, 20, 10, 35)
