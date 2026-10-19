import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import jwt

from app.core.config import settings
from app.core.errores import ErrorApi
from app.models import Usuario

ALGORITMO = "HS256"
CLAIMS_OBLIGATORIOS = ["sub", "rol", "token_version", "iat", "exp"]


@dataclass(frozen=True)
class ClaimsToken:
    usuario_id: uuid.UUID
    rol: str
    token_version: int
    expira_en: datetime


def sesion_invalida() -> ErrorApi:
    return ErrorApi(
        401, "NO_AUTENTICADO", "Tu sesión no es válida o expiró. Inicia sesión de nuevo."
    )


def crear_token(usuario: Usuario) -> str:
    """Emite el JWT de sesión con el rol y la versión de token vigente del usuario."""
    ahora = datetime.now(UTC)
    claims = {
        "sub": str(usuario.id),
        "rol": usuario.rol,
        "token_version": usuario.token_version,
        "iat": ahora,
        "exp": ahora + timedelta(minutes=settings.jwt_expires_minutes),
    }
    return jwt.encode(claims, settings.jwt_secret, algorithm=ALGORITMO)


def leer_token(token: str) -> ClaimsToken:
    """Verifica firma, vencimiento y claims; cualquier fallo es 401 NO_AUTENTICADO."""
    try:
        claims = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[ALGORITMO],
            options={"require": CLAIMS_OBLIGATORIOS},
        )
        return ClaimsToken(
            usuario_id=uuid.UUID(str(claims["sub"])),
            rol=str(claims["rol"]),
            token_version=int(claims["token_version"]),
            expira_en=datetime.fromtimestamp(int(claims["exp"]), UTC),
        )
    except (jwt.InvalidTokenError, ValueError, TypeError) as exc:
        raise sesion_invalida() from exc
