"""Motor de OCR (H24 CA03, TASK-85).

Las pruebas usan un motor de reemplazo, salvo la última: lee una imagen real con PaddleOCR y solo
corre si el grupo ocr está instalado (uv sync --group ocr). La CI no lo instala.
"""

import io
import logging
import sys
import time

import pytest
from PIL import Image, ImageDraw, ImageFont

from app.ocr import motor as modulo
from app.ocr.motor import (
    LADO_MAXIMO,
    ErrorOcr,
    LecturaOcr,
    Linea,
    MotorPaddle,
    leer_documento,
    paginas_de,
)


class MotorDePrueba:
    def __init__(self, lineas: list[Linea]) -> None:
        self.lineas = lineas
        self.leidas: list[Image.Image] = []

    def leer(self, imagen: Image.Image) -> list[Linea]:
        self.leidas.append(imagen)
        return self.lineas


def png(tamano: tuple[int, int]) -> bytes:
    salida = io.BytesIO()
    Image.new("RGB", tamano, "white").save(salida, "PNG")
    return salida.getvalue()


def test_la_lectura_une_el_texto_y_promedia_la_confianza() -> None:
    lectura = LecturaOcr([Linea("BCP", 0.9), Linea("S/ 85.40", 0.7)], paginas=1)

    assert lectura.texto == "BCP\nS/ 85.40"
    assert lectura.confianza == pytest.approx(0.8)
    assert LecturaOcr().confianza == 0.0


def test_una_foto_grande_se_reduce_antes_de_leer() -> None:
    (pagina,) = paginas_de(png((4000, 3000)), "png")

    assert max(pagina.size) == LADO_MAXIMO
    assert pagina.mode == "RGB"


def test_la_orientacion_exif_se_corrige() -> None:
    salida = io.BytesIO()
    exif = Image.Exif()
    exif[0x0112] = 6  # Rotada 90°: el celular guarda la foto acostada.
    Image.new("RGB", (300, 100), "white").save(salida, "JPEG", exif=exif)

    (pagina,) = paginas_de(salida.getvalue(), "jpg")

    assert pagina.size == (100, 300)


def test_una_imagen_que_no_abre_es_un_error_de_ocr() -> None:
    with pytest.raises(ErrorOcr):
        paginas_de(b"\x89PNG\r\n\x1a\nroto", "png")


def test_lee_cada_pagina_con_el_motor(monkeypatch: pytest.MonkeyPatch) -> None:
    lector = MotorDePrueba([Linea("Constancia de pago", 0.95)])
    monkeypatch.setattr(modulo, "motor", lambda: lector)

    lectura = leer_documento(png((800, 600)), "png")

    assert lectura.paginas == 1
    assert lectura.texto == "Constancia de pago"
    assert len(lector.leidas) == 1


def test_sin_paddleocr_el_motor_explica_como_instalarlo(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "paddleocr", None)

    with pytest.raises(ErrorOcr, match="uv sync --group ocr"):
        MotorPaddle()


def test_precargar_no_detiene_el_worker_si_falla(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    def fallar() -> None:
        raise ErrorOcr("sin modelo")

    monkeypatch.setattr(modulo, "motor", fallar)

    with caplog.at_level(logging.ERROR, logger="app.ocr"):
        modulo.precargar()

    assert "No se pudo precargar el modelo de OCR" in caplog.text


def test_un_pdf_lee_como_maximo_dos_paginas(monkeypatch: pytest.MonkeyPatch) -> None:
    pytest.importorskip("pdf2image")
    paginas = [Image.new("RGB", (600, 800), "white") for _ in range(4)]
    salida = io.BytesIO()
    paginas[0].save(salida, "PDF", save_all=True, append_images=paginas[1:])
    try:
        convertidas = paginas_de(salida.getvalue(), "pdf")
    except ErrorOcr:
        pytest.skip("poppler (pdftoppm) no está instalado")

    assert len(convertidas) == 2


def comprobante_sintetico() -> bytes:
    """Constancia inventada, sin datos reales, dibujada con la fuente del sistema."""
    lineas = [
        "BCP",
        "Constancia de pago de servicios",
        "Empresa: HIDRANDINA",
        "Codigo de suministro: 12345678",
        "Monto pagado: S/ 85.40",
        "Fecha: 20/10/2026 10:35",
        "Nro. de operacion: 00456789",
    ]
    imagen = Image.new("RGB", (900, 620), "white")
    dibujo = ImageDraw.Draw(imagen)
    try:
        fuente: ImageFont.FreeTypeFont | ImageFont.ImageFont = ImageFont.truetype(
            "DejaVuSans.ttf", 34
        )
    except OSError:
        try:
            fuente = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial.ttf", 34)
        except OSError:
            fuente = ImageFont.load_default(size=34)
    for i, texto in enumerate(lineas):
        dibujo.text((40, 40 + i * 80), texto, fill="black", font=fuente)
    salida = io.BytesIO()
    imagen.save(salida, "PNG")
    return salida.getvalue()


def test_paddleocr_lee_un_comprobante_de_una_pagina() -> None:
    """Medición del objetivo de 10 s con el modelo ya cargado (contrato H24, punto 7)."""
    pytest.importorskip("paddleocr")
    modulo.precargar()
    contenido = comprobante_sintetico()

    inicio = time.perf_counter()
    lectura = leer_documento(contenido, "png")
    segundos = time.perf_counter() - inicio

    assert "HIDRANDINA" in lectura.texto
    assert "85.40" in lectura.texto
    assert "00456789" in lectura.texto
    assert lectura.confianza > 0.9
    assert segundos < 10
