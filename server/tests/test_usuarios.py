from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.politica import VERSION
from app.core.seguridad import crear_token
from app.main import app
from app.models import Auditoria, Usuario
from tests.conftest import DosGerentes

PERFIL_URL = "/api/v1/usuarios/perfil"
POLITICA_URL = "/api/v1/usuarios/politica"
IP = "203.0.113.10"


def auth_headers(usuario: Usuario) -> dict[str, str]:
    return {"Authorization": f"Bearer {crear_token(usuario)}"}


@pytest.fixture
def cliente(db: Session) -> Iterator[TestClient]:
    app.dependency_overrides[get_db] = lambda: db
    yield TestClient(app, client=(IP, 50000))
    app.dependency_overrides.pop(get_db, None)


def test_ca01_nombres_y_apellidos_validos(cliente: TestClient, dos_gerentes: DosGerentes) -> None:
    """CA01: Permite nombres y apellidos con tildes, diéresis, ñ y espacios."""
    gerente = dos_gerentes.uno.gerente
    payload = {
        "nombres": "María José Ángel",
        "apellidos": "Ñañez Güere de la Flor",
        "celular": "987654321",
    }
    r = cliente.put(PERFIL_URL, json=payload, headers=auth_headers(gerente))
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["nombres"] == "María José Ángel"
    assert data["apellidos"] == "Ñañez Güere de la Flor"


@pytest.mark.parametrize(
    "nombres,apellidos",
    [
        ("Juan123", "Pérez"),
        ("Juan", "Pérez#"),
        ("", "Pérez"),
        ("Juan", ""),
        ("   ", "Pérez"),
        ("Juan", "   "),
        ("Juan_Carlos", "Pérez"),
    ],
)
def test_ca01_nombres_y_apellidos_invalidos(
    cliente: TestClient,
    dos_gerentes: DosGerentes,
    nombres: str,
    apellidos: str,
) -> None:
    """CA01: Rechaza nombres o apellidos vacíos, con números o caracteres especiales."""
    gerente = dos_gerentes.uno.gerente
    payload = {
        "nombres": nombres,
        "apellidos": apellidos,
        "celular": "987654321",
    }
    r = cliente.put(PERFIL_URL, json=payload, headers=auth_headers(gerente))
    assert r.status_code == 422


def test_ca06_celular_valido(cliente: TestClient, dos_gerentes: DosGerentes) -> None:
    """CA06: El celular es obligatorio, exactamente 9 dígitos que empiezan con 9."""
    gerente = dos_gerentes.uno.gerente
    payload = {
        "nombres": "Carlos",
        "apellidos": "Santillán",
        "celular": "912345678",
    }
    r = cliente.put(PERFIL_URL, json=payload, headers=auth_headers(gerente))
    assert r.status_code == 200, r.text
    assert r.json()["celular"] == "912345678"


@pytest.mark.parametrize(
    "celular",
    [
        "812345678",  # No empieza con 9
        "91234567",  # 8 dígitos
        "9123456789",  # 10 dígitos
        "91234567a",  # Contiene letras
        "9123-4567",  # Contiene guiones
        "",  # Vacío
    ],
)
def test_ca06_celular_invalido(
    cliente: TestClient,
    dos_gerentes: DosGerentes,
    celular: str,
) -> None:
    """CA06: Rechaza celulares que no tengan 9 dígitos numéricos empezando con 9."""
    gerente = dos_gerentes.uno.gerente
    payload = {
        "nombres": "Carlos",
        "apellidos": "Santillán",
        "celular": celular,
    }
    r = cliente.put(PERFIL_URL, json=payload, headers=auth_headers(gerente))
    assert r.status_code == 422


def test_ca09_rol_se_muestra_pero_no_se_edita(
    cliente: TestClient,
    dos_gerentes: DosGerentes,
    db: Session,
) -> None:
    """CA09: El rol se muestra en GET y no puede ser alterado con PUT."""
    asistente = dos_gerentes.uno.asistente
    headers = auth_headers(asistente)

    # 1. El rol se muestra en la consulta
    r_get = cliente.get(PERFIL_URL, headers=headers)
    assert r_get.status_code == 200
    assert r_get.json()["rol"] == "asistente"

    # 2. Intento de enviar 'rol': 'gerente' en la actualización
    payload = {
        "rol": "gerente",
        "nombres": "Ana",
        "apellidos": "Rojas",
        "celular": "999888777",
    }
    r_put = cliente.put(PERFIL_URL, json=payload, headers=headers)
    assert r_put.status_code == 200
    assert r_put.json()["rol"] == "asistente"
    assert r_put.json()["nombres"] == "Ana"

    # Verificar en base de datos
    db.refresh(asistente)
    assert asistente.rol == "asistente"


def test_ca11_aislamiento_de_usuarios(cliente: TestClient, dos_gerentes: DosGerentes) -> None:
    """CA11: Cada usuario solo ve y edita sus propios datos."""
    usuario_uno = dos_gerentes.uno.gerente
    usuario_dos = dos_gerentes.dos.gerente

    # Usuario 1 actualiza su perfil
    payload_uno = {
        "nombres": "Fernando",
        "apellidos": "Torres",
        "celular": "911222333",
    }
    r1 = cliente.put(PERFIL_URL, json=payload_uno, headers=auth_headers(usuario_uno))
    assert r1.status_code == 200
    assert r1.json()["id"] == str(usuario_uno.id)
    assert r1.json()["nombres"] == "Fernando"

    # Usuario 2 consulta su propio perfil y no ve los datos de usuario 1
    r2 = cliente.get(PERFIL_URL, headers=auth_headers(usuario_dos))
    assert r2.status_code == 200
    assert r2.json()["id"] == str(usuario_dos.id)
    assert r2.json()["nombres"] != "Fernando"

    # Sin autenticación responde 401
    r_unauth = cliente.get(PERFIL_URL)
    assert r_unauth.status_code == 401


def test_validaciones_documento(cliente: TestClient, dos_gerentes: DosGerentes) -> None:
    """Validaciones de formato para DNI (8 dígitos) y CE/Pasaporte (9-12 alfanuméricos)."""
    gerente = dos_gerentes.uno.gerente
    headers = auth_headers(gerente)

    # DNI válido
    r = cliente.put(
        PERFIL_URL,
        json={
            "nombres": "Valeria",
            "apellidos": "Mendoza",
            "celular": "955443322",
            "tipo_documento": "dni",
            "numero_documento": "12345678",
        },
        headers=headers,
    )
    assert r.status_code == 200
    assert r.json()["numero_documento"] == "12345678"

    # DNI con 7 dígitos (inválido)
    r = cliente.put(
        PERFIL_URL,
        json={
            "nombres": "Valeria",
            "apellidos": "Mendoza",
            "celular": "955443322",
            "tipo_documento": "dni",
            "numero_documento": "1234567",
        },
        headers=headers,
    )
    assert r.status_code == 422

    # CE válido
    r = cliente.put(
        PERFIL_URL,
        json={
            "nombres": "Valeria",
            "apellidos": "Mendoza",
            "celular": "955443322",
            "tipo_documento": "ce",
            "numero_documento": "ABC123456",
        },
        headers=headers,
    )
    assert r.status_code == 200

    # Tipo sin número
    r = cliente.put(
        PERFIL_URL,
        json={
            "nombres": "Valeria",
            "apellidos": "Mendoza",
            "celular": "955443322",
            "tipo_documento": "dni",
        },
        headers=headers,
    )
    assert r.status_code == 422


def test_conflicto_documento_y_correo_duplicado(
    cliente: TestClient,
    dos_gerentes: DosGerentes,
) -> None:
    """Rechaza documento o correo duplicado con código 409."""
    usuario_uno = dos_gerentes.uno.gerente
    usuario_dos = dos_gerentes.dos.gerente

    # Asignar documento y correo al usuario 1
    r1 = cliente.put(
        PERFIL_URL,
        json={
            "nombres": "Usuario",
            "apellidos": "Uno",
            "celular": "900000001",
            "tipo_documento": "dni",
            "numero_documento": "87654321",
            "correo": "usuario1@test.com",
        },
        headers=auth_headers(usuario_uno),
    )
    assert r1.status_code == 200

    # Usuario 2 intenta usar el mismo documento -> 409
    r2 = cliente.put(
        PERFIL_URL,
        json={
            "nombres": "Usuario",
            "apellidos": "Dos",
            "celular": "900000002",
            "tipo_documento": "dni",
            "numero_documento": "87654321",
        },
        headers=auth_headers(usuario_dos),
    )
    assert r2.status_code == 409
    assert r2.json()["code"] == "DOCUMENTO_DUPLICADO"

    # Usuario 2 intenta usar el mismo correo -> 409
    r3 = cliente.put(
        PERFIL_URL,
        json={
            "nombres": "Usuario",
            "apellidos": "Dos",
            "celular": "900000002",
            "correo": "USUARIO1@test.com",
        },
        headers=auth_headers(usuario_dos),
    )
    assert r3.status_code == 409
    assert r3.json()["code"] == "CORREO_DUPLICADO"


def test_aceptacion_de_politica_de_privacidad(
    cliente: TestClient,
    dos_gerentes: DosGerentes,
    db: Session,
) -> None:
    """Verifica endpoint específico de aceptación de política y su registro de auditoría."""
    gerente = dos_gerentes.uno.gerente
    r = cliente.post(
        POLITICA_URL,
        json={"version": VERSION},
        headers=auth_headers(gerente),
    )
    assert r.status_code == 200
    data = r.json()
    assert data["politica_version"] == VERSION
    assert data["politica_aceptada_en"] is not None

    # Verificar registro en auditoría
    evento = db.scalar(
        select(Auditoria)
        .where(
            Auditoria.usuario_id == gerente.id,
            Auditoria.accion == "politica_aceptada",
        )
        .order_by(Auditoria.creado_en.desc())
    )
    assert evento is not None
    assert evento.detalle == {"version": VERSION}


def test_auditoria_al_actualizar_perfil(
    cliente: TestClient,
    dos_gerentes: DosGerentes,
    db: Session,
) -> None:
    """Verifica que la actualización del perfil registre la auditoría con los cambios."""
    gerente = dos_gerentes.uno.gerente
    payload = {
        "nombres": "NuevoNombre",
        "apellidos": "NuevoApellido",
        "celular": "999111222",
    }
    r = cliente.put(PERFIL_URL, json=payload, headers=auth_headers(gerente))
    assert r.status_code == 200

    evento = db.scalar(
        select(Auditoria)
        .where(
            Auditoria.usuario_id == gerente.id,
            Auditoria.accion == "perfil_actualizado",
        )
        .order_by(Auditoria.creado_en.desc())
    )
    assert evento is not None
    assert "nombres" in evento.detalle
    assert evento.detalle["nombres"]["nuevo"] == "NuevoNombre"
    assert evento.detalle["celular"]["nuevo"] == "999111222"
