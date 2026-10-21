"""Almacenamiento privado S3 compartido por recibos y comprobantes."""

import hashlib
import io
import uuid
from dataclasses import dataclass

import boto3
from botocore.client import BaseClient
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError
from fastapi import UploadFile
from PIL import Image, UnidentifiedImageError

from app.core.config import settings
from app.core.errores import ErrorApi

MAXIMO_BYTES = 10 * 1024 * 1024
TIPOS = {"application/pdf": "pdf", "image/jpeg": "jpg", "image/png": "png"}
# Firma de los primeros bytes de cada tipo admitido. El tipo se decide por el contenido: el
# content_type lo declara el navegador y un archivo renombrado no debe pasar por otro.
FIRMAS = (
    (b"%PDF-", "application/pdf"),
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"\x89PNG\r\n\x1a\n", "image/png"),
)


@dataclass(frozen=True)
class ArchivoValidado:
    contenido: bytes
    extension: str
    tipo: str
    hash_sha256: str


def cliente_s3() -> BaseClient:
    return boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint,
        region_name=settings.s3_region,
        aws_access_key_id=settings.s3_access_key,
        aws_secret_access_key=settings.s3_secret_key,
        config=Config(signature_version="s3v4"),
    )


def tipo_por_contenido(contenido: bytes) -> str | None:
    for firma, tipo in FIRMAS:
        if contenido.startswith(firma):
            return tipo
    return None


def validar_contenido(contenido: bytes) -> ArchivoValidado:
    """Valida tamaño y tipo real de un archivo ya leído. Lanza 422 VALIDACION en el campo
    archivo si no es un PDF, JPG o PNG íntegro de hasta 10 MB."""
    if not contenido:
        raise ErrorApi(422, "VALIDACION", "El archivo está vacío.", "archivo")
    if len(contenido) > MAXIMO_BYTES:
        raise ErrorApi(422, "VALIDACION", "El archivo no puede superar 10 MB.", "archivo")
    tipo = tipo_por_contenido(contenido)
    if tipo is None:
        raise ErrorApi(422, "VALIDACION", "Solo se admiten PDF, JPG o PNG.", "archivo")
    if tipo == "application/pdf" and b"%%EOF" not in contenido[-2048:]:
        raise ErrorApi(422, "VALIDACION", "El PDF está incompleto o dañado.", "archivo")
    if tipo.startswith("image/"):
        try:
            with Image.open(io.BytesIO(contenido)) as imagen:
                if Image.MIME.get(imagen.format or "") != tipo:
                    raise UnidentifiedImageError
                imagen.verify()
        except (UnidentifiedImageError, OSError, Image.DecompressionBombError):
            raise ErrorApi(422, "VALIDACION", "La imagen no es válida.", "archivo") from None
    return ArchivoValidado(contenido, TIPOS[tipo], tipo, hashlib.sha256(contenido).hexdigest())


async def validar_archivo(archivo: UploadFile) -> ArchivoValidado:
    # Lee un byte más del límite para distinguir un archivo de 10 MB exactos de uno mayor.
    return validar_contenido(await archivo.read(MAXIMO_BYTES + 1))


def guardar_privado(ruta: str, archivo: ArchivoValidado) -> None:
    try:
        cliente_s3().put_object(
            Bucket=settings.s3_bucket,
            Key=ruta,
            Body=archivo.contenido,
            ContentType=archivo.tipo,
        )
    except (BotoCoreError, ClientError) as error:
        raise ErrorApi(503, "ARCHIVO_NO_DISPONIBLE", "No se pudo guardar el archivo.") from error


def leer_privado(ruta: str) -> bytes:
    """Contenido de un archivo privado, para procesarlo en el server (OCR). Al navegador se le
    entrega un enlace firmado, nunca el archivo por la API."""
    try:
        respuesta = cliente_s3().get_object(Bucket=settings.s3_bucket, Key=ruta)
        return bytes(respuesta["Body"].read())
    except (BotoCoreError, ClientError) as error:
        raise ErrorApi(503, "ARCHIVO_NO_DISPONIBLE", "No se pudo leer el archivo.") from error


def eliminar_privado(ruta: str) -> None:
    try:
        cliente_s3().delete_object(Bucket=settings.s3_bucket, Key=ruta)
    except (BotoCoreError, ClientError):
        pass


def ruta_comprobante(gerente_id: uuid.UUID, comprobante_id: uuid.UUID, extension: str) -> str:
    return f"comprobantes/{gerente_id}/{comprobante_id}.{extension}"


def enlace_firmado(ruta: str) -> str:
    try:
        return str(
            cliente_s3().generate_presigned_url(
                "get_object", Params={"Bucket": settings.s3_bucket, "Key": ruta}, ExpiresIn=300
            )
        )
    except (BotoCoreError, ClientError) as error:
        raise ErrorApi(503, "ARCHIVO_NO_DISPONIBLE", "No se pudo abrir el archivo.") from error
