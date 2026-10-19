import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import bcrypt
import jwt

from app.core.config import settings
from app.core.errores import ErrorApi
from app.models import Usuario

ALGORITMO = "HS256"
CLAIMS_OBLIGATORIOS = ["sub", "rol", "token_version", "iat", "exp"]
COSTO_BCRYPT = 12


def hashear_contrasena(contrasena: str) -> str:
    """Hash bcrypt de la contraseña. bcrypt rechaza más de 72 bytes: quien fija la contraseña
    debe validar su largo antes."""
    return bcrypt.hashpw(contrasena.encode(), bcrypt.gensalt(COSTO_BCRYPT)).decode()


def verificar_contrasena(contrasena: str, password_hash: str) -> bool:
    """Si la contraseña corresponde al hash. Una contraseña de más de 72 bytes o un hash que no
    es bcrypt no coinciden: no son un error del servidor."""
    try:
        return bcrypt.checkpw(contrasena.encode(), password_hash.encode())
    except ValueError:
        return False


# Hash con el mismo costo que los reales, calculado una vez al cargar el módulo. Verificar contra
# él cuando el usuario no existe iguala el tiempo de respuesta al de una cuenta real.
HASH_RELLENO = hashear_contrasena(secrets.token_urlsafe(32))


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
