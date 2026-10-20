import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.dependencias import (
    GerenteId,
    SesionDb,
    SoloAsistente,
    SoloGerente,
    UsuarioActual,
    obtener_propio,
)
from app.core.errores import registrar_manejadores
from app.core.seguridad import (
    COSTO_BCRYPT,
    HASH_RELLENO,
    crear_token,
    hashear_contrasena,
    leer_token,
    verificar_contrasena,
)
from app.models import Categoria, Usuario
from tests.conftest import DosGerentes

prueba = FastAPI()
registrar_manejadores(prueba)


@prueba.get("/yo")
def yo(usuario: UsuarioActual) -> dict[str, str]:
    return {"id": str(usuario.id), "rol": usuario.rol}


@prueba.get("/solo-gerente")
def solo_gerente(usuario: SoloGerente) -> dict[str, str]:
    return {"id": str(usuario.id)}


@prueba.get("/solo-asistente")
def solo_asistente(usuario: SoloAsistente) -> dict[str, str]:
    return {"id": str(usuario.id)}


@prueba.get("/gerente-propietario")
def gerente_propietario(gerente_id: GerenteId) -> dict[str, str]:
    return {"gerente_id": str(gerente_id)}


@prueba.get("/categorias/{categoria_id}")
def detalle_categoria(
    categoria_id: uuid.UUID, db: SesionDb, gerente_id: GerenteId
) -> dict[str, str]:
    categoria = obtener_propio(db, Categoria, categoria_id, gerente_id)
    return {"id": str(categoria.id), "nombre": categoria.nombre}


@pytest.fixture
def cliente(db: Session) -> Iterator[TestClient]:
    prueba.dependency_overrides[get_db] = lambda: db
    yield TestClient(prueba)
    prueba.dependency_overrides.clear()


def cabecera(usuario: Usuario) -> dict[str, str]:
    return {"Authorization": f"Bearer {crear_token(usuario)}"}


def token_con(claims: dict[str, object], clave: str | None = None) -> dict[str, str]:
    token = jwt.encode(claims, clave or settings.jwt_secret, algorithm="HS256")
    return {"Authorization": f"Bearer {token}"}


def claims_de(usuario: Usuario, **cambios: object) -> dict[str, object]:
    ahora = datetime.now(UTC)
    claims: dict[str, object] = {
        "sub": str(usuario.id),
        "rol": usuario.rol,
        "token_version": usuario.token_version,
        "iat": ahora,
        "exp": ahora + timedelta(minutes=5),
    }
    claims.update(cambios)
    return claims


def crear_categoria(db: Session, gerente: Usuario, nombre: str) -> Categoria:
    categoria = Categoria(gerente_id=gerente.id, nombre=nombre, tipo="servicio_variable")
    db.add(categoria)
    db.flush()
    return categoria


def assert_error(respuesta: Any, status: int, code: str, detail: str | None = None) -> None:
    assert respuesta.status_code == status
    cuerpo = respuesta.json()
    assert cuerpo["code"] == code
    assert cuerpo["field"] is None
    if detail is not None:
        assert cuerpo["detail"] == detail


# Token


def test_el_token_lleva_usuario_rol_version_y_vencimiento(dos_gerentes: DosGerentes) -> None:
    asistente = dos_gerentes.uno.asistente
    claims = jwt.decode(crear_token(asistente), settings.jwt_secret, algorithms=["HS256"])
    assert claims["sub"] == str(asistente.id)
    assert claims["rol"] == "asistente"
    assert claims["token_version"] == asistente.token_version
    assert claims["exp"] - claims["iat"] == settings.jwt_expires_minutes * 60
    assert leer_token(crear_token(asistente)).usuario_id == asistente.id


# Contraseñas


def test_la_contrasena_se_verifica_contra_su_hash() -> None:
    password_hash = hashear_contrasena("Clave-segura-1")
    assert password_hash != "Clave-segura-1"
    assert verificar_contrasena("Clave-segura-1", password_hash)
    assert not verificar_contrasena("clave-segura-1", password_hash)


def test_cada_hash_lleva_su_propia_sal() -> None:
    assert hashear_contrasena("Clave-segura-1") != hashear_contrasena("Clave-segura-1")


def test_un_hash_que_no_es_bcrypt_no_coincide() -> None:
    assert not verificar_contrasena("x", "x")


def test_una_contrasena_de_mas_de_72_bytes_no_coincide() -> None:
    password_hash = hashear_contrasena("a" * 72)
    assert not verificar_contrasena("a" * 73, password_hash)


def test_el_hash_de_relleno_usa_el_costo_de_los_reales() -> None:
    costo = f"$2b${COSTO_BCRYPT:02d}$"
    assert HASH_RELLENO.startswith(costo)
    assert hashear_contrasena("Clave-segura-1").startswith(costo)
    assert not verificar_contrasena("", HASH_RELLENO)


# 401 NO_AUTENTICADO


def test_sin_cabecera_responde_no_autenticado(cliente: TestClient) -> None:
    assert_error(cliente.get("/yo"), 401, "NO_AUTENTICADO", "Inicia sesión para continuar.")


def test_esquema_que_no_es_bearer_responde_no_autenticado(
    cliente: TestClient, dos_gerentes: DosGerentes
) -> None:
    token = crear_token(dos_gerentes.uno.gerente)
    r = cliente.get("/yo", headers={"Authorization": f"Basic {token}"})
    assert_error(r, 401, "NO_AUTENTICADO")


def test_token_mal_formado_responde_no_autenticado(cliente: TestClient) -> None:
    r = cliente.get("/yo", headers={"Authorization": "Bearer no-es-un-jwt"})
    assert_error(r, 401, "NO_AUTENTICADO")


def test_token_sin_claims_obligatorios_responde_no_autenticado(
    cliente: TestClient, dos_gerentes: DosGerentes
) -> None:
    claims = claims_de(dos_gerentes.uno.gerente)
    del claims["token_version"]
    assert_error(cliente.get("/yo", headers=token_con(claims)), 401, "NO_AUTENTICADO")


def test_sub_que_no_es_uuid_responde_no_autenticado(
    cliente: TestClient, dos_gerentes: DosGerentes
) -> None:
    claims = claims_de(dos_gerentes.uno.gerente, sub="no-es-uuid")
    assert_error(cliente.get("/yo", headers=token_con(claims)), 401, "NO_AUTENTICADO")


def test_firma_invalida_responde_no_autenticado(
    cliente: TestClient, dos_gerentes: DosGerentes
) -> None:
    cabeceras = token_con(claims_de(dos_gerentes.uno.gerente), "otra-clave-otra-clave-otra-clave")
    assert_error(cliente.get("/yo", headers=cabeceras), 401, "NO_AUTENTICADO")


def test_token_vencido_responde_no_autenticado(
    cliente: TestClient, dos_gerentes: DosGerentes
) -> None:
    hace_una_hora = datetime.now(UTC) - timedelta(hours=1)
    claims = claims_de(
        dos_gerentes.uno.gerente, iat=hace_una_hora, exp=hace_una_hora + timedelta(minutes=30)
    )
    assert_error(
        cliente.get("/yo", headers=token_con(claims)),
        401,
        "NO_AUTENTICADO",
        "Tu sesión no es válida o expiró. Inicia sesión de nuevo.",
    )


# 401 SESION_REVOCADA y CUENTA_INACTIVA


def test_token_version_desactualizado_responde_sesion_revocada(
    cliente: TestClient, db: Session, dos_gerentes: DosGerentes
) -> None:
    asistente = dos_gerentes.uno.asistente
    cabeceras = cabecera(asistente)
    asistente.token_version += 1
    db.flush()
    assert_error(
        cliente.get("/yo", headers=cabeceras),
        401,
        "SESION_REVOCADA",
        "Tu sesión fue cerrada. Inicia sesión de nuevo.",
    )


def test_cuenta_inactiva_responde_cuenta_inactiva(
    cliente: TestClient, db: Session, dos_gerentes: DosGerentes
) -> None:
    asistente = dos_gerentes.uno.asistente
    cabeceras = cabecera(asistente)
    asistente.estado = "inactiva"
    db.flush()
    assert_error(
        cliente.get("/yo", headers=cabeceras), 401, "CUENTA_INACTIVA", "Tu cuenta no está activa."
    )


def test_usuario_eliminado_responde_cuenta_inactiva(
    cliente: TestClient, db: Session, dos_gerentes: DosGerentes
) -> None:
    asistente = dos_gerentes.uno.asistente
    cabeceras = cabecera(asistente)
    asistente.eliminado_en = datetime.now(UTC)
    db.flush()
    assert_error(cliente.get("/yo", headers=cabeceras), 401, "CUENTA_INACTIVA")


def test_usuario_inexistente_responde_cuenta_inactiva(
    cliente: TestClient, dos_gerentes: DosGerentes
) -> None:
    claims = claims_de(dos_gerentes.uno.gerente, sub=str(uuid.uuid4()))
    assert_error(cliente.get("/yo", headers=token_con(claims)), 401, "CUENTA_INACTIVA")


def test_token_valido_devuelve_el_usuario(cliente: TestClient, dos_gerentes: DosGerentes) -> None:
    gerente = dos_gerentes.uno.gerente
    r = cliente.get("/yo", headers=cabecera(gerente))
    assert r.status_code == 200
    assert r.json() == {"id": str(gerente.id), "rol": "gerente"}


# 403 SIN_PERMISO


def test_asistente_no_entra_a_endpoint_de_gerente(
    cliente: TestClient, dos_gerentes: DosGerentes
) -> None:
    r = cliente.get("/solo-gerente", headers=cabecera(dos_gerentes.uno.asistente))
    assert_error(r, 403, "SIN_PERMISO", "No tienes permiso para realizar esta acción.")


def test_gerente_entra_a_endpoint_de_gerente(
    cliente: TestClient, dos_gerentes: DosGerentes
) -> None:
    gerente = dos_gerentes.uno.gerente
    r = cliente.get("/solo-gerente", headers=cabecera(gerente))
    assert r.status_code == 200
    assert r.json() == {"id": str(gerente.id)}


def test_gerente_no_entra_a_endpoint_de_asistente(
    cliente: TestClient, dos_gerentes: DosGerentes
) -> None:
    r = cliente.get("/solo-asistente", headers=cabecera(dos_gerentes.uno.gerente))
    assert_error(r, 403, "SIN_PERMISO")
    r = cliente.get("/solo-asistente", headers=cabecera(dos_gerentes.uno.asistente))
    assert r.status_code == 200


def test_el_rol_se_toma_de_la_base_y_no_del_token(
    cliente: TestClient, dos_gerentes: DosGerentes
) -> None:
    claims = claims_de(dos_gerentes.uno.asistente, rol="gerente")
    assert_error(cliente.get("/solo-gerente", headers=token_con(claims)), 403, "SIN_PERMISO")


# Gerente propietario y aislamiento entre gerentes


def test_gerente_propietario_de_gerentes_y_asistentes(
    cliente: TestClient, dos_gerentes: DosGerentes
) -> None:
    for equipo in (dos_gerentes.uno, dos_gerentes.dos):
        for usuario in (equipo.gerente, equipo.asistente):
            r = cliente.get("/gerente-propietario", headers=cabecera(usuario))
            assert r.json() == {"gerente_id": str(equipo.gerente.id)}


def test_gerente_y_su_asistente_ven_sus_recursos(
    cliente: TestClient, db: Session, dos_gerentes: DosGerentes
) -> None:
    categoria = crear_categoria(db, dos_gerentes.uno.gerente, "Luz")
    for usuario in (dos_gerentes.uno.gerente, dos_gerentes.uno.asistente):
        r = cliente.get(f"/categorias/{categoria.id}", headers=cabecera(usuario))
        assert r.status_code == 200
        assert r.json() == {"id": str(categoria.id), "nombre": "Luz"}


def test_otro_gerente_y_su_asistente_reciben_404_igual_que_inexistente(
    cliente: TestClient, db: Session, dos_gerentes: DosGerentes
) -> None:
    ajena = crear_categoria(db, dos_gerentes.uno.gerente, "Agua")
    crear_categoria(db, dos_gerentes.dos.gerente, "Agua")
    inexistente = cliente.get(
        f"/categorias/{uuid.uuid4()}", headers=cabecera(dos_gerentes.dos.gerente)
    )
    assert_error(inexistente, 404, "NO_ENCONTRADO", "No se encontró el recurso solicitado.")
    for usuario in (dos_gerentes.dos.gerente, dos_gerentes.dos.asistente):
        r = cliente.get(f"/categorias/{ajena.id}", headers=cabecera(usuario))
        assert r.status_code == 404
        assert r.json() == inexistente.json()


def test_id_que_no_es_uuid_responde_422_con_el_campo(
    cliente: TestClient, dos_gerentes: DosGerentes
) -> None:
    r = cliente.get("/categorias/abc", headers=cabecera(dos_gerentes.uno.gerente))
    assert r.status_code == 422
    assert r.json() == {
        "detail": "El valor no es válido.",
        "code": "VALIDACION",
        "field": "categoria_id",
    }
