"""Almacenamiento privado de archivos (H24 CA01, TASK-84).

El tipo se decide por el contenido, no por el content_type ni por la extensión. S3 se reemplaza
por un cliente en memoria: las pruebas no dependen de SeaweedFS.
"""

import io
import uuid
from typing import Any

import pytest
from botocore.exceptions import ClientError
from fastapi import UploadFile
from PIL import Image

from app.core.errores import ErrorApi
from app.services import archivos
from app.services.archivos import (
    MAXIMO_BYTES,
    eliminar_privado,
    enlace_firmado,
    guardar_privado,
    leer_privado,
    ruta_comprobante,
    validar_archivo,
    validar_contenido,
)


def imagen(formato: str, tamano: tuple[int, int] = (40, 30)) -> bytes:
    salida = io.BytesIO()
    Image.new("RGB", tamano, "white").save(salida, formato)
    return salida.getvalue()


def pdf() -> bytes:
    return imagen("PDF")


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


@pytest.mark.parametrize(
    ("contenido", "extension", "tipo"),
    [
        (imagen("PNG"), "png", "image/png"),
        (imagen("JPEG"), "jpg", "image/jpeg"),
        (pdf(), "pdf", "application/pdf"),
    ],
)
def test_acepta_pdf_jpg_y_png_por_su_contenido(contenido: bytes, extension: str, tipo: str) -> None:
    validado = validar_contenido(contenido)

    assert (validado.extension, validado.tipo) == (extension, tipo)
    assert len(validado.hash_sha256) == 64


def test_el_hash_identifica_el_mismo_archivo() -> None:
    contenido = imagen("PNG")
    assert validar_contenido(contenido).hash_sha256 == validar_contenido(contenido).hash_sha256
    assert validar_contenido(contenido).hash_sha256 != validar_contenido(imagen("JPEG")).hash_sha256


@pytest.mark.parametrize(
    ("contenido", "mensaje"),
    [
        (b"", "El archivo está vacío."),
        (b"GIF89a" + b"\x00" * 50, "Solo se admiten PDF, JPG o PNG."),
        (b"<html>no soy un pdf</html>", "Solo se admiten PDF, JPG o PNG."),
        (b"%PDF-1.7\n1 0 obj", "El PDF está incompleto o dañado."),
        (b"\x89PNG\r\n\x1a\n" + b"basura" * 20, "La imagen no es válida."),
        (b"\xff\xd8\xff" + b"basura" * 20, "La imagen no es válida."),
    ],
)
def test_rechaza_archivos_vacios_de_otro_tipo_o_danados(contenido: bytes, mensaje: str) -> None:
    with pytest.raises(ErrorApi) as error:
        validar_contenido(contenido)

    assert (error.value.status_code, error.value.code) == (422, "VALIDACION")
    assert (error.value.field, error.value.detail) == ("archivo", mensaje)


def test_acepta_10_mb_exactos_y_rechaza_uno_mas() -> None:
    base = pdf()
    relleno = MAXIMO_BYTES - len(base)
    # El relleno va antes del final del PDF para que siga terminando en %%EOF.
    cuerpo, fin = base[: -len(b"%%EOF\n")], base[-len(b"%%EOF\n") :]
    exacto = cuerpo + b" " * relleno + fin
    assert len(exacto) == MAXIMO_BYTES

    assert validar_contenido(exacto).tipo == "application/pdf"
    with pytest.raises(ErrorApi, match="10 MB"):
        validar_contenido(exacto + b" ")


def test_valida_el_archivo_subido_sin_confiar_en_su_content_type() -> None:
    # Un PNG enviado como PDF se guarda como PNG; texto enviado como imagen se rechaza.
    png = UploadFile(io.BytesIO(imagen("PNG")), headers={"content-type": "application/pdf"})
    assert validar_archivo(png).extension == "png"

    texto = UploadFile(io.BytesIO(b"hola"), headers={"content-type": "image/png"})
    with pytest.raises(ErrorApi, match="Solo se admiten"):
        validar_archivo(texto)


def test_guarda_lee_y_elimina_en_la_ruta_privada(s3: S3EnMemoria) -> None:
    validado = validar_contenido(imagen("PNG"))
    ruta = ruta_comprobante(uuid.uuid4(), uuid.uuid4(), validado.extension)

    guardar_privado(ruta, validado)
    assert s3.objetos[ruta] == (validado.contenido, "image/png")
    assert leer_privado(ruta) == validado.contenido

    eliminar_privado(ruta)
    assert ruta not in s3.objetos


def test_la_ruta_separa_comprobantes_por_gerente() -> None:
    gerente_id, comprobante_id = uuid.uuid4(), uuid.uuid4()

    ruta = ruta_comprobante(gerente_id, comprobante_id, "pdf")

    assert ruta == f"comprobantes/{gerente_id}/{comprobante_id}.pdf"


def test_un_fallo_de_s3_responde_503_sin_detalles(s3: S3EnMemoria) -> None:
    s3.falla = True
    validado = validar_contenido(imagen("PNG"))

    for operacion in (
        lambda: guardar_privado("comprobantes/x.png", validado),
        lambda: leer_privado("comprobantes/x.png"),
        lambda: enlace_firmado("comprobantes/x.png"),
    ):
        with pytest.raises(ErrorApi) as error:
            operacion()
        assert (error.value.status_code, error.value.code) == (503, "ARCHIVO_NO_DISPONIBLE")
        assert "caído" not in error.value.detail


def test_eliminar_no_falla_si_s3_no_responde(s3: S3EnMemoria) -> None:
    s3.falla = True
    eliminar_privado("comprobantes/x.png")


def test_el_enlace_firmado_vence_en_cinco_minutos(s3: S3EnMemoria) -> None:
    assert enlace_firmado("comprobantes/a.pdf") == "https://s3.local/comprobantes/a.pdf?expira=300"


def test_el_cliente_usa_la_configuracion_de_s3() -> None:
    cliente = archivos.cliente_s3()

    assert cliente.meta.endpoint_url == archivos.settings.s3_endpoint
    assert cliente.meta.region_name == archivos.settings.s3_region
