"""Regresiones de validación e historial entre cambios y restablecimientos reales por API."""

import hashlib
import secrets
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.seguridad import crear_token, hashear_contrasena, verificar_contrasena
from app.main import app
from app.models import HistorialContrasena, TokenRestablecimiento, Usuario
from tests.conftest import DosGerentes

ACTUAL = "Actual-segura-1"
ANTERIORES = ["Anterior-uno-1", "Anterior-dos-2", "Anterior-tres-3", "Anterior-cuatro-4"]
HASHES = {clave: hashear_contrasena(clave) for clave in [ACTUAL, *ANTERIORES]}


@pytest.fixture
def cliente(db: Session) -> Iterator[TestClient]:
    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app, raise_server_exceptions=False) as cliente:
        yield cliente
    app.dependency_overrides.pop(get_db, None)


@pytest.fixture
def usuario(db: Session, dos_gerentes: DosGerentes) -> Usuario:
    usuario = dos_gerentes.uno.gerente
    usuario.password_hash = HASHES[ACTUAL]
    db.flush()
    return usuario


def restablecimiento(db: Session, usuario: Usuario) -> tuple[str, TokenRestablecimiento]:
    codigo = secrets.token_urlsafe(32)
    registro = TokenRestablecimiento(
        usuario_id=usuario.id,
        token_hash=hashlib.sha256(codigo.encode()).hexdigest(),
        expira_en=datetime.now(UTC) + timedelta(minutes=20),
    )
    db.add(registro)
    db.flush()
    return codigo, registro


def enviar(
    cliente: TestClient, db: Session, usuario: Usuario, flujo: str, nueva: str, actual: str = ACTUAL
):
    if flujo == "asistente":
        return cliente.post(
            "/api/v1/asistentes",
            headers={"Authorization": f"Bearer {crear_token(usuario)}"},
            json={"nombres": "Ana", "apellidos": "Paz", "contrasena": nueva},
        )
    if flujo == "cambio":
        return cliente.post(
            "/api/v1/me/contrasena",
            headers={"Authorization": f"Bearer {crear_token(usuario)}"},
            json={"contrasena_actual": actual, "contrasena_nueva": nueva},
        )
    codigo, _ = restablecimiento(db, usuario)
    return cliente.post(
        "/api/v1/auth/restablecer-contrasena",
        json={"token": codigo, "nueva_contrasena": nueva},
    )


@pytest.mark.parametrize("flujo", ["cambio", "restablecimiento", "asistente"])
@pytest.mark.parametrize(
    ("nueva", "motivo"),
    [
        ("abcdefgh", "mayúscula"),
        ("Aa1!aaa", "al menos 8"),
        ("Aa1!" + "a" * 69, "demasiado larga"),
        ("Ññ1!" * 13, "demasiado larga"),
    ],
)
def test_reglas_informan_motivo_sin_cambiar_cuenta(
    cliente: TestClient, db: Session, usuario: Usuario, flujo: str, nueva: str, motivo: str
) -> None:
    r = enviar(cliente, db, usuario, flujo, nueva)

    assert r.status_code == 422
    assert r.json()["code"] == "VALIDACION"
    assert (
        r.json()["field"]
        == {
            "cambio": "contrasena_nueva",
            "restablecimiento": "nueva_contrasena",
            "asistente": "contrasena",
        }[flujo]
    )
    assert motivo in r.json()["detail"]
    assert nueva not in r.text
    assert usuario.password_hash == HASHES[ACTUAL]
    assert usuario.token_version == 0
    assert list(db.scalars(select(HistorialContrasena))) == []
    assert all(t.usado_en is None for t in db.scalars(select(TokenRestablecimiento)))


@pytest.mark.parametrize("flujo", ["cambio", "restablecimiento"])
@pytest.mark.parametrize("nueva", ["Aa1!" + "a" * 68, "Ññ1!" + "a" * 66])
def test_acepta_el_limite_de_72_bytes_y_archiva_solo_la_anterior(
    cliente: TestClient, db: Session, usuario: Usuario, flujo: str, nueva: str
) -> None:
    assert len(nueva.encode()) == 72
    r = enviar(cliente, db, usuario, flujo, nueva)

    assert r.status_code == 200, r.text
    assert verificar_contrasena(nueva, usuario.password_hash)
    assert usuario.token_version == 1
    assert list(db.scalars(select(HistorialContrasena.password_hash))) == [HASHES[ACTUAL]]


def historial_antiguo(db: Session, usuario: Usuario) -> None:
    # Del más antiguo al más reciente: el formato anterior dejaba duplicados y el hash vigente.
    claves = [*reversed(ANTERIORES), ANTERIORES[0], ACTUAL, ACTUAL]
    for i, clave in enumerate(claves):
        db.add(
            HistorialContrasena(
                usuario_id=usuario.id,
                password_hash=HASHES[clave],
                creado_en=datetime(2026, 1, 1, tzinfo=UTC) + timedelta(days=i),
            )
        )
    db.flush()


@pytest.mark.parametrize("flujo", ["cambio", "restablecimiento"])
@pytest.mark.parametrize("nueva", [ACTUAL, *ANTERIORES[:3]])
def test_rechaza_actual_y_tres_anteriores_con_historial_antiguo(
    cliente: TestClient, db: Session, usuario: Usuario, flujo: str, nueva: str
) -> None:
    historial_antiguo(db, usuario)
    r = enviar(cliente, db, usuario, flujo, nueva)

    assert r.status_code == (422 if flujo == "cambio" else 400)
    assert r.json()["code"] == "CONTRASENA_REPETIDA"
    assert r.json()["field"] == ("contrasena_nueva" if flujo == "cambio" else "nueva_contrasena")
    assert usuario.password_hash == HASHES[ACTUAL]
    assert usuario.token_version == 0
    assert all(t.usado_en is None for t in db.scalars(select(TokenRestablecimiento)))


@pytest.mark.parametrize("flujo", ["cambio", "restablecimiento"])
def test_cuarta_anterior_se_puede_usar_sin_borrar_historial_antiguo(
    cliente: TestClient, db: Session, usuario: Usuario, flujo: str
) -> None:
    historial_antiguo(db, usuario)
    r = enviar(cliente, db, usuario, flujo, ANTERIORES[3])

    assert r.status_code == 200, r.text
    assert verificar_contrasena(ANTERIORES[3], usuario.password_hash)
    assert len(list(db.scalars(select(HistorialContrasena)))) == 8


@pytest.mark.parametrize("flujo", ["cambio", "restablecimiento"])
def test_alternar_flujos_conserva_tres_anteriores(
    cliente: TestClient, db: Session, usuario: Usuario, flujo: str
) -> None:
    anteriores = [ACTUAL, "Segunda-clave-2", "Tercera-clave-3", "Cuarta-clave-4"]
    for i, paso in enumerate(["cambio", "restablecimiento", "cambio"]):
        r = enviar(cliente, db, usuario, paso, anteriores[i + 1], anteriores[i])
        assert r.status_code == 200, r.text

    r = enviar(cliente, db, usuario, flujo, ACTUAL, anteriores[-1])

    assert r.json()["code"] == "CONTRASENA_REPETIDA"
    assert usuario.token_version == 3
    hashes = list(db.scalars(select(HistorialContrasena.password_hash)))
    assert len(hashes) == 3
    assert all(any(verificar_contrasena(clave, h) for h in hashes) for clave in anteriores[:3])


@pytest.mark.parametrize("flujo", ["cambio", "restablecimiento"])
def test_historial_ajeno_no_restringe_la_cuenta(
    cliente: TestClient, db: Session, usuario: Usuario, dos_gerentes: DosGerentes, flujo: str
) -> None:
    db.add(
        HistorialContrasena(
            usuario_id=dos_gerentes.dos.gerente.id,
            password_hash=HASHES[ANTERIORES[0]],
        )
    )
    db.flush()
    r = enviar(cliente, db, usuario, flujo, ANTERIORES[0])
    assert r.status_code == 200, r.text


def test_validacion_no_consume_token_y_permite_corregir(
    cliente: TestClient, db: Session, usuario: Usuario
) -> None:
    codigo, registro = restablecimiento(db, usuario)
    ruta = "/api/v1/auth/restablecer-contrasena"
    r = cliente.post(ruta, json={"token": codigo, "nueva_contrasena": "abcdefgh"})
    assert r.status_code == 422
    assert registro.usado_en is None

    r = cliente.post(ruta, json={"token": codigo, "nueva_contrasena": "Corregida-clave-2"})
    assert r.status_code == 200
    assert registro.usado_en is not None

    r = cliente.post(ruta, json={"token": codigo, "nueva_contrasena": "Otra-clave-3"})
    assert r.status_code == 400
    assert r.json()["code"] == "TOKEN_INVALIDO"
