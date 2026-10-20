import logging
from collections.abc import Mapping

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

from app.core.reglas import ErrorReglaContrasena

logger = logging.getLogger(__name__)

CODIGOS_HTTP = {
    401: "NO_AUTENTICADO",
    403: "SIN_PERMISO",
    404: "NO_ENCONTRADO",
    405: "METODO_NO_PERMITIDO",
    409: "CONFLICTO",
}

MENSAJES_HTTP = {
    401: "Inicia sesión para continuar.",
    403: "No tienes permiso para realizar esta acción.",
    404: "No se encontró el recurso solicitado.",
    405: "Método no permitido.",
}

MENSAJES_VALIDACION = {
    "missing": "Este campo es obligatorio.",
    "json_invalid": "El cuerpo de la solicitud no es un JSON válido.",
}

UBICACIONES = {"body", "query", "path", "header", "cookie"}


class ErrorApi(Exception):
    """Error de negocio que sale como {detail, code, field} con su status HTTP."""

    def __init__(self, status_code: int, code: str, detail: str, field: str | None = None) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.code = code
        self.detail = detail
        self.field = field


def respuesta(
    status_code: int,
    detail: str,
    code: str,
    field: str | None = None,
    headers: Mapping[str, str] | None = None,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"detail": detail, "code": code, "field": field},
        headers=headers,
    )


async def manejar_error_api(_: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, ErrorApi):
        raise exc
    return respuesta(exc.status_code, exc.detail, exc.code, exc.field)


async def manejar_validacion(_: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, RequestValidationError):
        raise exc
    # El formato admite un solo campo: se informa el primer error.
    error = exc.errors()[0]
    tipo = error.get("type", "")
    mensaje = MENSAJES_VALIDACION.get(tipo, "El valor no es válido.")
    causa = error.get("ctx", {}).get("error")
    if isinstance(causa, ErrorReglaContrasena):
        mensaje = str(causa)
    if tipo == "json_invalid":
        # En un JSON mal formado la ubicación es la posición del carácter, no un campo.
        return respuesta(422, mensaje, "VALIDACION")
    partes = [str(p) for p in error.get("loc", ()) if p not in UBICACIONES]
    return respuesta(422, mensaje, "VALIDACION", ".".join(partes) or None)


async def manejar_http(_: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, HTTPException):
        raise exc
    codigo = CODIGOS_HTTP.get(exc.status_code, "ERROR_HTTP")
    mensaje = MENSAJES_HTTP.get(exc.status_code, str(exc.detail))
    return respuesta(exc.status_code, mensaje, codigo, headers=exc.headers)


async def manejar_inesperado(_: Request, exc: Exception) -> JSONResponse:
    logger.exception("Error inesperado", exc_info=exc)
    return respuesta(500, "Ocurrió un error inesperado. Intenta de nuevo.", "ERROR_INTERNO")


def registrar_manejadores(app: FastAPI) -> None:
    app.add_exception_handler(ErrorApi, manejar_error_api)
    app.add_exception_handler(RequestValidationError, manejar_validacion)
    app.add_exception_handler(HTTPException, manejar_http)
    app.add_exception_handler(Exception, manejar_inesperado)
