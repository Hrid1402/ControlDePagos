import logging
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.seguridad import crear_token, hashear_contrasena, leer_token
from app.main import app
from app.models import Auditoria, Usuario
from tests.conftest import DosGerentes

LOGIN = "/api/v1/auth/login"
IP = "203.0.113.7"
CONTRASENA = "Clave-segura-1"
# Un solo hash para todo el módulo: bcrypt es lento a propósito.
HASH = hashear_contrasena(CONTRASENA)

CREDENCIALES_INVALIDAS = {
    "detail": "Usuario o contraseña incorrectos.",
    "code": "CREDENCIALES_INVALIDAS",
    "field": None,
}
CUENTA_INACTIVA = {
    "detail": "Cuenta inactiva, contacta al gerente.",
    "code": "CUENTA_INACTIVA",
    "field": None,
}


def bloqueada(minutos: str) -> dict[str, Any]:
    return {
        "detail": f"Tu cuenta está bloqueada por intentos fallidos. Intenta de nuevo en {minutos}.",
        "code": "CUENTA_BLOQUEADA",
        "field": None,
    }


@pytest.fixture
def cliente(db: Session) -> Iterator[TestClient]:
    # Sin with: no arranca el ciclo de vida, que se suscribe a Redis y el login no usa.
    app.dependency_overrides[get_db] = lambda: db
    yield TestClient(app, client=(IP, 50000))
    app.dependency_overrides.clear()


@pytest.fixture
def equipos(db: Session, dos_gerentes: DosGerentes) -> DosGerentes:
    """Los dos gerentes y sus asistentes con la contraseña CONTRASENA."""
    for equipo in (dos_gerentes.uno, dos_gerentes.dos):
        equipo.gerente.password_hash = HASH
        equipo.asistente.password_hash = HASH
    db.flush()
    return dos_gerentes


def ingresar(cliente: TestClient, username: str, contrasena: str = CONTRASENA) -> httpx.Response:
    return cliente.post(LOGIN, json={"username": username, "contrasena": contrasena})


def eventos_de(db: Session, usuario: Usuario) -> list[Auditoria]:
    return list(db.scalars(select(Auditoria).where(Auditoria.usuario_id == usuario.id)))


def contar_eventos(db: Session) -> int:
    return db.scalar(select(func.count()).select_from(Auditoria)) or 0


def fallar(cliente: TestClient, usuario: Usuario, veces: int) -> None:
    for _ in range(veces):
        assert ingresar(cliente, usuario.username, "incorrecta").status_code == 401


# Ingreso correcto (CA01)


@pytest.mark.parametrize("rol", ["gerente", "asistente"])
def test_cada_rol_ingresa_con_usuario_y_contrasena(
    cliente: TestClient, db: Session, equipos: DosGerentes, rol: str
) -> None:
    usuario = getattr(equipos.uno, rol)
    r = ingresar(cliente, usuario.username)
    assert r.status_code == 200
    cuerpo = r.json()
    assert cuerpo["token_type"] == "bearer"
    assert cuerpo["usuario"] == {"id": str(usuario.id), "nombre": usuario.username, "rol": rol}
    claims = leer_token(cuerpo["access_token"])
    assert claims.usuario_id == usuario.id
    assert claims.rol == rol
    db.refresh(usuario)
    assert usuario.ultimo_ingreso is not None
    [evento] = eventos_de(db, usuario)
    assert evento.accion == "login_exitoso"
    assert evento.gerente_id == equipos.uno.gerente.id
    assert str(evento.ip) == IP


def test_el_nombre_usa_nombres_y_apellidos(
    cliente: TestClient, db: Session, equipos: DosGerentes
) -> None:
    gerente = equipos.uno.gerente
    gerente.nombres, gerente.apellidos = "Ana", "Pérez"
    db.flush()
    assert ingresar(cliente, gerente.username).json()["usuario"]["nombre"] == "Ana Pérez"


def test_el_usuario_no_distingue_mayusculas_ni_espacios(
    cliente: TestClient, equipos: DosGerentes
) -> None:
    r = ingresar(cliente, f"  {equipos.uno.gerente.username.upper()} ")
    assert r.status_code == 200


def test_la_contrasena_distingue_mayusculas_y_espacios(
    cliente: TestClient, equipos: DosGerentes
) -> None:
    username = equipos.uno.gerente.username
    assert ingresar(cliente, username, CONTRASENA.upper()).status_code == 401
    assert ingresar(cliente, username, f" {CONTRASENA}").status_code == 401


def test_ingresar_reinicia_el_contador(
    cliente: TestClient, db: Session, equipos: DosGerentes
) -> None:
    gerente = equipos.uno.gerente
    fallar(cliente, gerente, 3)
    assert ingresar(cliente, gerente.username).status_code == 200
    db.refresh(gerente)
    assert gerente.intentos_fallidos == 0
    assert gerente.bloqueado_hasta is None


# Credenciales incorrectas: mensaje genérico (CA04)


def test_contrasena_incorrecta_responde_generico_y_cuenta_el_intento(
    cliente: TestClient, db: Session, equipos: DosGerentes
) -> None:
    asistente = equipos.uno.asistente
    r = ingresar(cliente, asistente.username, "incorrecta")
    assert r.status_code == 401
    assert r.json() == CREDENCIALES_INVALIDAS
    db.refresh(asistente)
    assert asistente.intentos_fallidos == 1
    [evento] = eventos_de(db, asistente)
    assert evento.accion == "login_fallido"
    assert evento.gerente_id == equipos.uno.gerente.id
    assert evento.detalle == {
        "motivo": "contrasena_incorrecta",
        "intentos_fallidos": 1,
        "bloqueado_hasta": None,
    }


def test_el_intento_fallido_se_confirma_antes_del_401(
    cliente: TestClient, db: Session, equipos: DosGerentes
) -> None:
    gerente = equipos.uno.gerente
    assert ingresar(cliente, gerente.username, "incorrecta").status_code == 401
    # Lo no confirmado se deshace con el rollback; el intento y su evento ya estaban confirmados.
    gerente.nombres = "sin confirmar"
    db.flush()
    db.rollback()
    db.refresh(gerente)
    assert gerente.nombres is None
    assert gerente.intentos_fallidos == 1
    assert len(eventos_de(db, gerente)) == 1


def test_usuario_inexistente_responde_igual_que_contrasena_incorrecta(
    cliente: TestClient, db: Session, equipos: DosGerentes, caplog: pytest.LogCaptureFixture
) -> None:
    incorrecta = ingresar(cliente, equipos.uno.gerente.username, "incorrecta")
    antes = contar_eventos(db)
    with caplog.at_level(logging.WARNING, logger="app.auditoria"):
        inexistente = ingresar(cliente, "NombreQueNoExiste", "OtraClave123")
    assert inexistente.status_code == 401
    assert inexistente.json() == incorrecta.json()
    assert contar_eventos(db) == antes
    [registro] = [r for r in caplog.records if r.name == "app.auditoria"]
    assert getattr(registro, "evento", None) == "login_desconocido"
    assert "NombreQueNoExiste" not in caplog.text
    assert "OtraClave123" not in caplog.text


def test_una_contrasena_de_mas_de_72_bytes_es_incorrecta(
    cliente: TestClient, db: Session, equipos: DosGerentes
) -> None:
    gerente = equipos.uno.gerente
    r = ingresar(cliente, gerente.username, "a" * 100)
    assert r.status_code == 401
    assert r.json() == CREDENCIALES_INVALIDAS
    db.refresh(gerente)
    assert gerente.intentos_fallidos == 1


def test_el_fallo_queda_en_la_auditoria_de_su_gerente(
    cliente: TestClient, db: Session, equipos: DosGerentes
) -> None:
    fallar(cliente, equipos.dos.asistente, 1)
    [evento] = eventos_de(db, equipos.dos.asistente)
    assert evento.gerente_id == equipos.dos.gerente.id
    vistos_por_uno = db.scalars(
        select(Auditoria).where(Auditoria.gerente_id == equipos.uno.gerente.id)
    ).all()
    assert vistos_por_uno == []


# Bloqueo tras 5 intentos durante 15 minutos (CA06)


def test_el_quinto_fallo_bloquea_15_minutos(
    cliente: TestClient, db: Session, equipos: DosGerentes
) -> None:
    gerente = equipos.uno.gerente
    fallar(cliente, gerente, 4)
    r = ingresar(cliente, gerente.username, "incorrecta")
    assert r.status_code == 423
    assert r.json() == bloqueada("15 minutos")
    db.refresh(gerente)
    assert gerente.intentos_fallidos == 5
    assert gerente.bloqueado_hasta is not None
    restante = gerente.bloqueado_hasta - datetime.now(UTC)
    assert timedelta(minutes=14) < restante <= timedelta(minutes=15)


@pytest.mark.parametrize("contrasena", [CONTRASENA, "incorrecta"])
def test_la_cuenta_bloqueada_no_ingresa_ni_cuenta_intentos(
    cliente: TestClient, db: Session, equipos: DosGerentes, contrasena: str
) -> None:
    gerente = equipos.uno.gerente
    hasta = datetime.now(UTC) + timedelta(minutes=14, seconds=30)
    gerente.intentos_fallidos, gerente.bloqueado_hasta = 5, hasta
    db.flush()
    r = ingresar(cliente, gerente.username, contrasena)
    assert r.status_code == 423
    assert r.json() == bloqueada("15 minutos")
    db.refresh(gerente)
    assert gerente.intentos_fallidos == 5
    assert gerente.bloqueado_hasta == hasta
    [evento] = eventos_de(db, gerente)
    assert evento.detalle["motivo"] == "cuenta_bloqueada"


def test_el_ultimo_minuto_se_informa_en_singular(
    cliente: TestClient, db: Session, equipos: DosGerentes
) -> None:
    gerente = equipos.uno.gerente
    gerente.intentos_fallidos = 5
    gerente.bloqueado_hasta = datetime.now(UTC) + timedelta(seconds=20)
    db.flush()
    assert ingresar(cliente, gerente.username).json() == bloqueada("1 minuto")


def test_al_terminar_el_bloqueo_se_ingresa_y_se_reinicia(
    cliente: TestClient, db: Session, equipos: DosGerentes
) -> None:
    gerente = equipos.uno.gerente
    gerente.intentos_fallidos = 5
    gerente.bloqueado_hasta = datetime.now(UTC) - timedelta(seconds=1)
    db.flush()
    assert ingresar(cliente, gerente.username).status_code == 200
    db.refresh(gerente)
    assert gerente.intentos_fallidos == 0
    assert gerente.bloqueado_hasta is None


def test_al_terminar_el_bloqueo_el_contador_vuelve_a_empezar(
    cliente: TestClient, db: Session, equipos: DosGerentes
) -> None:
    gerente = equipos.uno.gerente
    gerente.intentos_fallidos = 5
    gerente.bloqueado_hasta = datetime.now(UTC) - timedelta(seconds=1)
    db.flush()
    r = ingresar(cliente, gerente.username, "incorrecta")
    assert r.json() == CREDENCIALES_INVALIDAS
    db.refresh(gerente)
    assert gerente.intentos_fallidos == 1
    assert gerente.bloqueado_hasta is None


# Cuenta inactiva (CA07) y eliminada


@pytest.mark.parametrize("rol", ["gerente", "asistente"])
def test_la_cuenta_inactiva_con_contrasena_correcta_lo_informa(
    cliente: TestClient, db: Session, equipos: DosGerentes, rol: str
) -> None:
    usuario = getattr(equipos.uno, rol)
    usuario.estado = "inactiva"
    db.flush()
    r = ingresar(cliente, usuario.username)
    assert r.status_code == 403
    assert r.json() == CUENTA_INACTIVA
    db.refresh(usuario)
    assert usuario.intentos_fallidos == 0
    assert usuario.ultimo_ingreso is None
    [evento] = eventos_de(db, usuario)
    assert evento.detalle["motivo"] == "cuenta_inactiva"


def test_la_cuenta_inactiva_con_contrasena_incorrecta_responde_generico(
    cliente: TestClient, db: Session, equipos: DosGerentes
) -> None:
    asistente = equipos.uno.asistente
    asistente.estado = "inactiva"
    db.flush()
    r = ingresar(cliente, asistente.username, "incorrecta")
    assert r.json() == CREDENCIALES_INVALIDAS
    db.refresh(asistente)
    assert asistente.intentos_fallidos == 1


@pytest.mark.parametrize("contrasena", [CONTRASENA, "incorrecta"])
def test_la_cuenta_inactiva_y_bloqueada_responde_423_sin_revelar_que_esta_inactiva(
    cliente: TestClient, db: Session, equipos: DosGerentes, contrasena: str
) -> None:
    # El bloqueo se revisa antes que la contraseña y el estado: mientras dure, nadie averigua
    # si la cuenta está inactiva ni si la contraseña era correcta.
    asistente = equipos.uno.asistente
    asistente.estado = "inactiva"
    asistente.intentos_fallidos = 5
    asistente.bloqueado_hasta = datetime.now(UTC) + timedelta(minutes=10)
    db.flush()
    r = ingresar(cliente, asistente.username, contrasena)
    assert r.status_code == 423
    assert r.json() == bloqueada("10 minutos")
    db.refresh(asistente)
    assert asistente.intentos_fallidos == 5
    [evento] = eventos_de(db, asistente)
    assert evento.detalle["motivo"] == "cuenta_bloqueada"


@pytest.mark.parametrize("contrasena", [CONTRASENA, "incorrecta"])
def test_la_cuenta_eliminada_responde_generico_sin_contar_intento(
    cliente: TestClient, db: Session, equipos: DosGerentes, contrasena: str
) -> None:
    asistente = equipos.uno.asistente
    asistente.estado = "inactiva"
    asistente.eliminado_en = datetime.now(UTC)
    db.flush()
    r = ingresar(cliente, asistente.username, contrasena)
    assert r.status_code == 401
    assert r.json() == CREDENCIALES_INVALIDAS
    db.refresh(asistente)
    assert asistente.intentos_fallidos == 0
    [evento] = eventos_de(db, asistente)
    assert evento.accion == "login_fallido"
    assert evento.gerente_id == equipos.uno.gerente.id
    assert evento.detalle["motivo"] == "cuenta_eliminada"


# Validación


@pytest.mark.parametrize(
    ("cuerpo", "campo", "mensaje"),
    [
        ({"contrasena": CONTRASENA}, "username", "Este campo es obligatorio."),
        ({"username": "gerente_uno"}, "contrasena", "Este campo es obligatorio."),
        ({"username": "   ", "contrasena": CONTRASENA}, "username", "El valor no es válido."),
        ({"username": "gerente_uno", "contrasena": ""}, "contrasena", "El valor no es válido."),
    ],
)
def test_los_campos_vacios_se_marcan(
    cliente: TestClient, equipos: DosGerentes, cuerpo: dict[str, str], campo: str, mensaje: str
) -> None:
    r = cliente.post(LOGIN, json=cuerpo)
    assert r.status_code == 422
    assert r.json() == {"detail": mensaje, "code": "VALIDACION", "field": campo}


# Renovación del token


RENOVAR = "/api/v1/auth/renovar"


def token_emitido_hace(usuario: Usuario, minutos: int) -> str:
    """Token de sesión emitido hace unos minutos, con sus 30 minutos de vigencia desde entonces."""
    emitido = datetime.now(UTC) - timedelta(minutes=minutos)
    claims = {
        "sub": str(usuario.id),
        "rol": usuario.rol,
        "token_version": usuario.token_version,
        "iat": emitido,
        "exp": emitido + timedelta(minutes=settings.jwt_expires_minutes),
    }
    return jwt.encode(claims, settings.jwt_secret, algorithm="HS256")


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.parametrize("rol", ["gerente", "asistente"])
def test_renovar_devuelve_un_token_nuevo_que_vence_despues(
    cliente: TestClient, dos_gerentes: DosGerentes, rol: str
) -> None:
    usuario = getattr(dos_gerentes.uno, rol)
    anterior = token_emitido_hace(usuario, 10)
    r = cliente.post(RENOVAR, headers=bearer(anterior))
    assert r.status_code == 200
    cuerpo = r.json()
    assert cuerpo["token_type"] == "bearer"
    assert cuerpo["usuario"] == {"id": str(usuario.id), "nombre": usuario.username, "rol": rol}
    nuevo = cuerpo["access_token"]
    assert nuevo != anterior
    claims = leer_token(nuevo)
    assert claims.usuario_id == usuario.id
    assert claims.token_version == usuario.token_version
    assert claims.expira_en > leer_token(anterior).expira_en


def test_renovar_sin_token_responde_no_autenticado(cliente: TestClient) -> None:
    r = cliente.post(RENOVAR)
    assert r.status_code == 401
    assert r.json()["code"] == "NO_AUTENTICADO"


def test_renovar_con_token_vencido_responde_no_autenticado(
    cliente: TestClient, dos_gerentes: DosGerentes
) -> None:
    r = cliente.post(RENOVAR, headers=bearer(token_emitido_hace(dos_gerentes.uno.gerente, 31)))
    assert r.status_code == 401
    assert r.json()["code"] == "NO_AUTENTICADO"


def test_renovar_con_sesion_revocada_responde_sesion_revocada(
    cliente: TestClient, db: Session, dos_gerentes: DosGerentes
) -> None:
    asistente = dos_gerentes.uno.asistente
    token = crear_token(asistente)
    asistente.token_version += 1
    db.flush()
    r = cliente.post(RENOVAR, headers=bearer(token))
    assert r.status_code == 401
    assert r.json()["code"] == "SESION_REVOCADA"


def test_renovar_con_cuenta_desactivada_responde_cuenta_inactiva(
    cliente: TestClient, db: Session, dos_gerentes: DosGerentes
) -> None:
    asistente = dos_gerentes.uno.asistente
    token = crear_token(asistente)
    asistente.estado = "inactiva"
    db.flush()
    r = cliente.post(RENOVAR, headers=bearer(token))
    assert r.status_code == 401
    assert r.json()["code"] == "CUENTA_INACTIVA"


# Usuario de la sesión


ME = "/api/v1/auth/me"


@pytest.mark.parametrize("rol", ["gerente", "asistente"])
def test_me_devuelve_el_usuario_de_la_sesion(
    cliente: TestClient, dos_gerentes: DosGerentes, rol: str
) -> None:
    usuario = getattr(dos_gerentes.dos, rol)
    r = cliente.get(ME, headers=bearer(crear_token(usuario)))
    assert r.status_code == 200
    assert r.json() == {"id": str(usuario.id), "nombre": usuario.username, "rol": rol}


def test_me_sin_token_responde_no_autenticado(cliente: TestClient) -> None:
    r = cliente.get(ME)
    assert r.status_code == 401
    assert r.json()["code"] == "NO_AUTENTICADO"


def test_me_con_sesion_revocada_responde_sesion_revocada(
    cliente: TestClient, db: Session, dos_gerentes: DosGerentes
) -> None:
    gerente = dos_gerentes.uno.gerente
    token = crear_token(gerente)
    gerente.token_version += 1
    db.flush()
    r = cliente.get(ME, headers=bearer(token))
    assert r.status_code == 401
    assert r.json()["code"] == "SESION_REVOCADA"
