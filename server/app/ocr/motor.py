"""OCR de comprobantes con PaddleOCR (H24, TASK-85).

leer_documento convierte el archivo en imágenes y devuelve el texto por línea con su confianza.
No usa IA generativa: solo detección y reconocimiento de texto.

- PDF: solo las primeras MAXIMO_PAGINAS páginas, a PDF_DPI. Un comprobante tiene una página; el
  límite evita que un PDF largo ocupe el worker. Requiere poppler (pdftoppm) en el sistema.
- Imágenes: se corrige la orientación EXIF y se reducen a LADO_MAXIMO píxeles; una foto de
  celular de 4000 px no lee mejor y tarda varias veces más.
- El modelo se carga una vez por proceso. El worker de la cola ocr lo precarga al iniciar
  (settings.ocr_precargar), así la primera lectura no paga la carga de unos 10 s.

El tiempo máximo de una lectura lo pone la tarea de Celery (soft_time_limit), no este módulo.
"""

import io
import logging
import threading
from dataclasses import dataclass, field
from functools import cache
from typing import Any, Protocol

from PIL import Image, ImageOps

logger = logging.getLogger("app.ocr")

MAXIMO_PAGINAS = 2
PDF_DPI = 200
LADO_MAXIMO = 2000
IDIOMA = "es"


class ErrorOcr(Exception):
    """El archivo no se pudo convertir o leer. La tarea decide si reintenta."""


@dataclass(frozen=True)
class Linea:
    texto: str
    confianza: float


@dataclass(frozen=True)
class LecturaOcr:
    lineas: list[Linea] = field(default_factory=list)
    paginas: int = 0

    @property
    def texto(self) -> str:
        return "\n".join(linea.texto for linea in self.lineas)

    @property
    def confianza(self) -> float:
        """Confianza media de las líneas; 0 si no se leyó nada."""
        if not self.lineas:
            return 0.0
        return sum(linea.confianza for linea in self.lineas) / len(self.lineas)


class Motor(Protocol):
    def leer(self, imagen: Image.Image) -> list[Linea]: ...


class MotorPaddle:
    """PaddleOCR 3 en CPU con el modelo de español. Sin clasificador de orientación del documento
    ni corrección de deformación: los comprobantes son fotos o capturas planas y esos modelos
    duplican el tiempo de lectura."""

    def __init__(self) -> None:
        try:
            from paddleocr import PaddleOCR
        except ImportError as error:
            raise ErrorOcr(
                "PaddleOCR no está instalado: ejecuta uv sync --group ocr en server/."
            ) from error
        self._ocr: Any = PaddleOCR(
            lang=IDIOMA,
            use_doc_orientation_classify=False,
            use_doc_unwarping=False,
            use_textline_orientation=False,
        )
        # Una instancia de Paddle no admite lecturas simultáneas desde varios hilos.
        self._bloqueo = threading.Lock()

    def leer(self, imagen: Image.Image) -> list[Linea]:
        import numpy as np

        # PaddleOCR espera BGR, como OpenCV.
        matriz = np.asarray(imagen.convert("RGB"))[:, :, ::-1]
        with self._bloqueo:
            resultados = self._ocr.predict(matriz)
        lineas = []
        for resultado in resultados:
            for texto, confianza in zip(
                resultado["rec_texts"], resultado["rec_scores"], strict=True
            ):
                if texto.strip():
                    lineas.append(Linea(texto.strip(), float(confianza)))
        return lineas


@cache
def motor() -> Motor:
    return MotorPaddle()


def precargar() -> None:
    """Carga el modelo en el proceso actual. Si falla, el worker sigue arrancado y cada lectura
    vuelve a intentarlo: el error queda en el log."""
    try:
        motor()
    except Exception:
        logger.exception("No se pudo precargar el modelo de OCR")


def reducir(imagen: Image.Image) -> Image.Image:
    imagen = ImageOps.exif_transpose(imagen) or imagen
    imagen.thumbnail((LADO_MAXIMO, LADO_MAXIMO))
    return imagen.convert("RGB")


def paginas_de(contenido: bytes, extension: str) -> list[Image.Image]:
    if extension == "pdf":
        try:
            from pdf2image import convert_from_bytes
            from pdf2image.exceptions import PDFInfoNotInstalledError, PDFPageCountError

            paginas = convert_from_bytes(
                contenido, dpi=PDF_DPI, first_page=1, last_page=MAXIMO_PAGINAS
            )
        except ImportError as error:
            raise ErrorOcr("pdf2image no está instalado: uv sync --group ocr.") from error
        except (PDFInfoNotInstalledError, PDFPageCountError) as error:
            raise ErrorOcr("No se pudo convertir el PDF en imágenes.") from error
        return [reducir(pagina) for pagina in paginas]
    try:
        return [reducir(Image.open(io.BytesIO(contenido)))]
    except OSError as error:
        raise ErrorOcr("No se pudo abrir la imagen.") from error


def leer_documento(contenido: bytes, extension: str) -> LecturaOcr:
    paginas = paginas_de(contenido, extension)
    lector = motor()
    lineas: list[Linea] = []
    for pagina in paginas:
        lineas.extend(lector.leer(pagina))
    return LecturaOcr(lineas, len(paginas))
