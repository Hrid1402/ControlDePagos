"""Servicio común de auditoría (H34): toda acción que cambia datos se registra aquí.

El registro va en la misma transacción que la acción auditada: se agrega y se envía a la base
con flush, pero el commit lo hace quien llama. Si la acción se deshace, el evento también.
"""

import logging
import uuid
from collections.abc import Mapping
from datetime import date, datetime, time
from decimal import Decimal
from enum import StrEnum
from typing import Any

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from app.core.dependencias import Origen, gerente_de
from app.core.errores import ErrorApi
from app.models import Auditoria, Usuario

# Registro técnico: eventos que no tienen gerente al que pertenecer.
logger = logging.getLogger("app.auditoria")


class Accion(StrEnum):
    """Acciones auditadas. Cada historia agrega aquí las suyas."""

    LOGIN_EXITOSO = "login_exitoso"
    LOGIN_FALLIDO = "login_fallido"
    CUENTA_CREADA = "cuenta_creada"
    CUENTA_ACTIVADA = "cuenta_activada"
    CUENTA_DESACTIVADA = "cuenta_desactivada"
    CUENTA_ELIMINADA = "cuenta_eliminada"
    DEUDA_MONTO_CAMBIADO = "deuda_monto_cambiado"
    DEUDA_ESTADO_CAMBIADO = "deuda_estado_cambiado"
    CONTRASENA_RESTABLECIDA = "contrasena_restablecida"
    PAGO_INICIADO = "pago_iniciado"
    PAGO_INICIO_CANCELADO = "pago_inicio_cancelado"
    APROBACION_SOLICITADA = "aprobacion_solicitada"
    PERFIL_ACTUALIZADO = "perfil_actualizado"
    POLITICA_ACEPTADA = "politica_aceptada"
    DEUDA_FIJADA = "deuda_fijada"
    DEUDA_POSPUESTA = "deuda_pospuesta"
    ORDEN_VISTA = "orden_vista"
    ORDEN_ACEPTADA = "orden_aceptada"
    ORDEN_RECHAZADA = "orden_rechazada"
    USUARIO_CAMBIADO = "usuario_cambiado"
    CONTRASENA_CAMBIADA = "contrasena_cambiada"


# Una clave que contiene alguno de estos fragmentos no se guarda en el detalle.
FRAGMENTOS_SECRETOS = (
    "password",
    "contrasena",
    "contraseña",
    "token",
    "secret",
    "clave",
    "api_key",
)
# Claves que contienen un fragmento pero no son secretas.
CLAVES_PERMITIDAS = frozenset({"token_version"})


def es_secreto(clave: str) -> bool:
    normal = clave.lower()
    return normal not in CLAVES_PERMITIDAS and any(f in normal for f in FRAGMENTOS_SECRETOS)


def limpiar(valor: Any) -> Any:
    """Quita los secretos y convierte el valor a JSON. Los montos Decimal se guardan como texto
    para no perder exactitud; un tipo no previsto es un error de programación."""
    if isinstance(valor, Mapping):
        limpio = {}
        for clave, interno in valor.items():
            if not isinstance(clave, str):
                raise TypeError(f"Las claves del detalle deben ser texto: {clave!r}.")
            if not es_secreto(clave):
                limpio[clave] = limpiar(interno)
        return limpio
    if isinstance(valor, list | tuple):
        return [limpiar(v) for v in valor]
    if valor is None or isinstance(valor, str | bool | int):
        return valor
    if isinstance(valor, Decimal | uuid.UUID):
        return str(valor)
    if isinstance(valor, datetime | date | time):
        return valor.isoformat()
    raise TypeError(f"El detalle de auditoría no admite valores {type(valor).__name__}.")


def diferencias(anterior: Mapping[str, Any], nuevo: Mapping[str, Any]) -> dict[str, Any]:
    """Campos que cambiaron, con su valor anterior y el nuevo. Omite los secretos."""
    claves = list(anterior) + [c for c in nuevo if c not in anterior]
    return {
        clave: {"anterior": limpiar(anterior.get(clave)), "nuevo": limpiar(nuevo.get(clave))}
        for clave in claves
        if not es_secreto(clave) and anterior.get(clave) != nuevo.get(clave)
    }


def nombre_de(usuario: Usuario) -> str:
    """Nombre que se copia al registro para conservarlo si la cuenta se elimina."""
    nombres = (usuario.nombres or "").strip()
    apellidos = (usuario.apellidos or "").strip()
    if nombres and apellidos:
        return f"{nombres} {apellidos}"
    return usuario.username


def registrar_auditoria(
    db: Session,
    usuario: Usuario,
    accion: Accion,
    entidad: str,
    entidad_id: uuid.UUID | None,
    detalle: Mapping[str, Any] | None = None,
    *,
    origen: Origen,
) -> Auditoria:
    """Inserta un evento de auditoría. entidad es el nombre de la tabla afectada."""
    gerente_id = gerente_de(usuario)
    if gerente_id is None:
        raise ValueError("No se puede auditar a una asistente sin gerente.")
    registro = Auditoria(
        gerente_id=gerente_id,
        usuario_id=usuario.id,
        usuario_nombre=nombre_de(usuario),
        accion=accion.value,
        entidad=entidad,
        entidad_id=entidad_id,
        detalle=limpiar(detalle or {}),
        dispositivo=origen.dispositivo,
        ip=origen.ip,
    )
    db.add(registro)
    db.flush()
    return registro


def registrar_login_desconocido(origen: Origen) -> None:
    """Ingreso con un usuario que no existe. No va a la tabla porque no hay gerente al que
    asignarlo; va al registro técnico. No recibe el nombre escrito: podría ser una contraseña
    escrita en el campo equivocado."""
    dispositivo = origen.dispositivo
    if dispositivo is not None:
        # El User-Agent lo escribe el cliente: sin saltos de línea no puede fingir otra entrada.
        dispositivo = dispositivo.replace("\r", "").replace("\n", "")
    logger.warning(
        "Ingreso fallido con una cuenta desconocida (ip=%s, dispositivo=%r)",
        origen.ip,
        dispositivo,
        extra={"evento": "login_desconocido"},
    )


def consulta_historial(usuario: Usuario) -> Select[Auditoria]:
    """Historial global del gerente, del más reciente al más antiguo. La asistente no tiene
    acceso; el detalle de una deuda ofrece aparte solo sus eventos autorizados."""
    if usuario.rol != "gerente":
        raise ErrorApi(403, "SIN_PERMISO", "No tienes permiso para realizar esta acción.")
    return (
        select(Auditoria)
        .where(Auditoria.gerente_id == usuario.id)
        .order_by(Auditoria.creado_en.desc(), Auditoria.id.desc())
    )
