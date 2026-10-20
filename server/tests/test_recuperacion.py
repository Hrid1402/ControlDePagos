import hashlib
import secrets
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.seguridad import hashear_contrasena
from app.main import app
from app.models import Auditoria, HistorialContrasena, TokenRestablecimiento
from tests.conftest import DosGerentes

SOLICITAR = "/api/v1/auth/recuperar-contrasena"
RESTABLECER = "/api/v1/auth/restablecer-contrasena"
LOGIN = "/api/v1/auth/login"
IP = "203.0.113.7"
CONTRASENA_INICIAL = "Clave-inicial-1"
HASH_INICIAL = hashear_contrasena(CONTRASENA_INICIAL)


@pytest.fixture
def cliente(db: Session) -> Iterator[TestClient]:
    app.dependency_overrides[get_db] = lambda: db
    yield TestClient(app, client=(IP, 50000))
    app.dependency_overrides.clear()


@pytest.fixture
def equipos(db: Session, dos_gerentes: DosGerentes) -> DosGerentes:
    for equipo in (dos_gerentes.uno, dos_gerentes.dos):
        equipo.gerente.password_hash = HASH_INICIAL
        equipo.asistente.password_hash = HASH_INICIAL
        equipo.gerente.correo = f"{equipo.gerente.username}@example.com"
        equipo.asistente.correo = f"{equipo.asistente.username}@example.com"
    db.flush()
    return dos_gerentes


def test_solicitar_recuperacion_con_correo_existente_crea_token(
    cliente: TestClient, db: Session, equipos: DosGerentes
) -> None:
    gerente = equipos.uno.gerente
    r = cliente.post(SOLICITAR, json={"correo": gerente.correo})
    assert r.status_code == 200
    assert "Si el correo está registrado" in r.json()["detail"]

    token_db = db.scalar(
        select(TokenRestablecimiento).where(TokenRestablecimiento.usuario_id == gerente.id)
    )
    assert token_db is not None
    assert token_db.usado_en is None
    assert token_db.expira_en > datetime.now(UTC)


def test_solicitar_recuperacion_con_correo_inexistente_responde_generico(
    cliente: TestClient, db: Session
) -> None:
    r = cliente.post(SOLICITAR, json={"correo": "nadie@example.com"})
    assert r.status_code == 200
    assert "Si el correo está registrado" in r.json()["detail"]

    total = len(db.scalars(select(TokenRestablecimiento)).all())
    assert total == 0


def test_solicitar_recuperacion_con_cuenta_inactiva_no_genera_token(
    cliente: TestClient, db: Session, equipos: DosGerentes
) -> None:
    asistente = equipos.uno.asistente
    asistente.estado = "inactiva"
    db.flush()

    r = cliente.post(SOLICITAR, json={"correo": asistente.correo})
    assert r.status_code == 200

    token_db = db.scalar(
        select(TokenRestablecimiento).where(TokenRestablecimiento.usuario_id == asistente.id)
    )
    assert token_db is None


def test_restablecer_contrasena_exitoso(
    cliente: TestClient, db: Session, equipos: DosGerentes
) -> None:
    gerente = equipos.uno.gerente
    token_crudo = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(token_crudo.encode()).hexdigest()
    version_previa = gerente.token_version

    registro = TokenRestablecimiento(
        usuario_id=gerente.id,
        token_hash=token_hash,
        expira_en=datetime.now(UTC) + timedelta(hours=1),
    )
    db.add(registro)
    db.commit()

    nueva_clave = "Nueva-clave-segura-99"
    r = cliente.post(
        RESTABLECER,
        json={"token": token_crudo, "nueva_contrasena": nueva_clave},
    )
    assert r.status_code == 200
    assert "Contraseña restablecida exitosamente" in r.json()["detail"]

    db.refresh(registro)
    assert registro.usado_en is not None

    db.refresh(gerente)
    assert gerente.token_version == version_previa + 1
    assert gerente.intentos_fallidos == 0
    assert gerente.bloqueado_hasta is None

    # Verifica que la nueva contraseña funcione para ingresar
    r_login_nuevo = cliente.post(
        LOGIN, json={"username": gerente.username, "contrasena": nueva_clave}
    )
    assert r_login_nuevo.status_code == 200

    # Verifica que la contraseña anterior ya no funcione
    r_login_viejo = cliente.post(
        LOGIN, json={"username": gerente.username, "contrasena": CONTRASENA_INICIAL}
    )
    assert r_login_viejo.status_code == 401

    # Verifica que se guardó en el historial de contraseñas
    historial = db.scalars(
        select(HistorialContrasena).where(HistorialContrasena.usuario_id == gerente.id)
    ).all()
    assert len(historial) >= 1

    # Verifica auditoría
    eventos = db.scalars(
        select(Auditoria).where(
            Auditoria.usuario_id == gerente.id,
            Auditoria.accion == "contrasena_restablecida",
        )
    ).all()
    assert len(eventos) == 1


def test_restablecer_con_token_inexistente_responde_400(cliente: TestClient) -> None:
    r = cliente.post(
        RESTABLECER,
        json={"token": "token-falso-inexistente", "nueva_contrasena": "NuevaClave123"},
    )
    assert r.status_code == 400
    assert r.json()["code"] == "TOKEN_INVALIDO"


def test_restablecer_con_token_ya_usado_responde_400(
    cliente: TestClient, db: Session, equipos: DosGerentes
) -> None:
    gerente = equipos.uno.gerente
    token_crudo = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(token_crudo.encode()).hexdigest()

    registro = TokenRestablecimiento(
        usuario_id=gerente.id,
        token_hash=token_hash,
        expira_en=datetime.now(UTC) + timedelta(hours=1),
        usado_en=datetime.now(UTC) - timedelta(minutes=5),
    )
    db.add(registro)
    db.commit()

    r = cliente.post(
        RESTABLECER,
        json={"token": token_crudo, "nueva_contrasena": "NuevaClave123"},
    )
    assert r.status_code == 400
    assert r.json()["code"] == "TOKEN_INVALIDO"


def test_restablecer_con_token_vencido_responde_400(
    cliente: TestClient, db: Session, equipos: DosGerentes
) -> None:
    gerente = equipos.uno.gerente
    token_crudo = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(token_crudo.encode()).hexdigest()

    registro = TokenRestablecimiento(
        usuario_id=gerente.id,
        token_hash=token_hash,
        expira_en=datetime.now(UTC) - timedelta(minutes=10),
    )
    db.add(registro)
    db.commit()

    r = cliente.post(
        RESTABLECER,
        json={"token": token_crudo, "nueva_contrasena": "NuevaClave123"},
    )
    assert r.status_code == 400
    assert r.json()["code"] == "TOKEN_INVALIDO"


def test_restablecer_con_contrasena_corta_responde_422(cliente: TestClient) -> None:
    r = cliente.post(
        RESTABLECER,
        json={"token": "un-token-valido-aqui", "nueva_contrasena": "corta"},
    )
    assert r.status_code == 422
    assert r.json()["code"] == "VALIDACION"
    assert r.json()["field"] == "nueva_contrasena"


def test_restablecer_no_permite_reutilizar_contrasena_actual_ni_ultimas_3(
    cliente: TestClient, db: Session, equipos: DosGerentes
) -> None:
    gerente = equipos.uno.gerente
    # Insertar contraseñas previas en el historial
    clave_vieja_1 = "Clave-vieja-uno-1"
    clave_vieja_2 = "Clave-vieja-dos-2"
    clave_vieja_3 = "Clave-vieja-tres-3"
    clave_vieja_4 = "Clave-vieja-cuatro-4"

    for c in [clave_vieja_4, clave_vieja_3, clave_vieja_2, clave_vieja_1]:
        db.add(HistorialContrasena(usuario_id=gerente.id, password_hash=hashear_contrasena(c)))
        db.flush()
    db.commit()

    # Intentar restablecer con la contraseña actual
    token_1 = secrets.token_urlsafe(32)
    db.add(
        TokenRestablecimiento(
            usuario_id=gerente.id,
            token_hash=hashlib.sha256(token_1.encode()).hexdigest(),
            expira_en=datetime.now(UTC) + timedelta(hours=1),
        )
    )
    db.commit()

    r = cliente.post(RESTABLECER, json={"token": token_1, "nueva_contrasena": CONTRASENA_INICIAL})
    assert r.status_code == 400
    assert r.json()["code"] == "CONTRASENA_REPETIDA"

    # Intentar restablecer con la última contraseña del historial
    token_2 = secrets.token_urlsafe(32)
    db.add(
        TokenRestablecimiento(
            usuario_id=gerente.id,
            token_hash=hashlib.sha256(token_2.encode()).hexdigest(),
            expira_en=datetime.now(UTC) + timedelta(hours=1),
        )
    )
    db.commit()

    r2 = cliente.post(RESTABLECER, json={"token": token_2, "nueva_contrasena": clave_vieja_1})
    assert r2.status_code == 400
    assert r2.json()["code"] == "CONTRASENA_REPETIDA"

    # Intentar restablecer con la 4ta contraseña vieja (ya no está entre las últimas 3)
    token_3 = secrets.token_urlsafe(32)
    db.add(
        TokenRestablecimiento(
            usuario_id=gerente.id,
            token_hash=hashlib.sha256(token_3.encode()).hexdigest(),
            expira_en=datetime.now(UTC) + timedelta(hours=1),
        )
    )
    db.commit()

    r3 = cliente.post(RESTABLECER, json={"token": token_3, "nueva_contrasena": clave_vieja_4})
    assert r3.status_code == 200
