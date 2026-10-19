import ipaddress
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Annotated, Protocol

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.errores import ErrorApi
from app.core.seguridad import leer_token
from app.models import Usuario

SesionDb = Annotated[Session, Depends(get_db)]

esquema_bearer = HTTPBearer(auto_error=False)


def usuario_desde_token(db: Session, token: str) -> Usuario:
    """Resuelve el usuario de un token. Reutilizable fuera de HTTP, por ejemplo en WebSocket."""
    claims = leer_token(token)
    usuario = db.get(Usuario, claims.usuario_id)
    if usuario is None or usuario.eliminado_en is not None or usuario.estado != "activa":
        raise ErrorApi(401, "CUENTA_INACTIVA", "Tu cuenta no está activa.")
    if usuario.token_version != claims.token_version:
        raise ErrorApi(401, "SESION_REVOCADA", "Tu sesión fue cerrada. Inicia sesión de nuevo.")
    return usuario


def obtener_usuario_actual(
    db: SesionDb,
    credenciales: Annotated[HTTPAuthorizationCredentials | None, Depends(esquema_bearer)],
) -> Usuario:
    if credenciales is None:
        raise ErrorApi(401, "NO_AUTENTICADO", "Inicia sesión para continuar.")
    return usuario_desde_token(db, credenciales.credentials)


UsuarioActual = Annotated[Usuario, Depends(obtener_usuario_actual)]


def requerir_rol(*roles: str) -> Callable[[Usuario], Usuario]:
    """Crea una dependencia que solo deja pasar a los roles indicados (403 SIN_PERMISO)."""

    def verificar(usuario: UsuarioActual) -> Usuario:
        if usuario.rol not in roles:
            raise ErrorApi(403, "SIN_PERMISO", "No tienes permiso para realizar esta acción.")
        return usuario

    return verificar


SoloGerente = Annotated[Usuario, Depends(requerir_rol("gerente"))]
SoloAsistente = Annotated[Usuario, Depends(requerir_rol("asistente"))]


def gerente_de(usuario: Usuario) -> uuid.UUID | None:
    """Gerente propietario de los datos: el propio gerente o el gerente de la asistente."""
    return usuario.id if usuario.rol == "gerente" else usuario.gerente_id


def obtener_gerente_id(usuario: UsuarioActual) -> uuid.UUID:
    gerente_id = gerente_de(usuario)
    if gerente_id is None:
        raise ErrorApi(403, "SIN_PERMISO", "No tienes permiso para realizar esta acción.")
    return gerente_id


GerenteId = Annotated[uuid.UUID, Depends(obtener_gerente_id)]

LARGO_MAXIMO_DISPOSITIVO = 300


@dataclass(frozen=True)
class Origen:
    """Desde dónde llega una solicitud: navegador o aplicación (User-Agent) e IP."""

    dispositivo: str | None
    ip: ipaddress.IPv4Address | ipaddress.IPv6Address | None


def obtener_origen(request: Request) -> Origen:
    """Lee el User-Agent y la IP del cliente. No usa X-Forwarded-For porque se puede falsificar:
    detrás de un proxy, uvicorn debe arrancar con --proxy-headers."""
    agente = request.headers.get("user-agent")
    dispositivo = agente[:LARGO_MAXIMO_DISPOSITIVO] if agente else None
    ip = None
    if request.client is not None:
        try:
            ip = ipaddress.ip_address(request.client.host)
        except ValueError:
            # Un host que no es IP, como el "testclient" de las pruebas, no cabe en inet.
            ip = None
    return Origen(dispositivo=dispositivo, ip=ip)


OrigenSolicitud = Annotated[Origen, Depends(obtener_origen)]


class DeGerente(Protocol):
    @property
    def gerente_id(self) -> uuid.UUID | None: ...


def obtener_propio[M: DeGerente](
    db: Session, modelo: type[M], recurso_id: uuid.UUID, gerente_id: uuid.UUID
) -> M:
    """Devuelve el recurso del gerente; si no existe o es ajeno responde el mismo 404."""
    recurso = db.get(modelo, recurso_id)
    if recurso is None or recurso.gerente_id != gerente_id:
        raise ErrorApi(404, "NO_ENCONTRADO", "No se encontró el recurso solicitado.")
    return recurso
