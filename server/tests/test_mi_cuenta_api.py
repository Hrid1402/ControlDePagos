"""API que necesita la pantalla Mi cuenta (TASK-9, H02): señales del perfil, correo y política."""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core import politica
from app.core.database import get_db
from app.core.seguridad import crear_token, hashear_contrasena
from app.main import app
from app.models import Usuario
from tests.conftest import DosGerentes

PERFIL_URL = "/api/v1/usuarios/perfil"
POLITICA_URL = "/api/v1/usuarios/politica"
CLAVE = "Clave-Actual-2026"


def auth(usuario: Usuario) -> dict[str, str]:
    return {"Authorization": f"Bearer {crear_token(usuario)}"}


@pytest.fixture
def cliente(db: Session) -> Iterator[TestClient]:
    app.dependency_overrides[get_db] = lambda: db
    yield TestClient(app)
    app.dependency_overrides.pop(get_db, None)


def datos(**cambios: object) -> dict[str, object]:
    return {"nombres": "Ana", "apellidos": "Rojas", "celular": "987654321", **cambios}


def test_el_perfil_informa_cambios_restantes_contrasena_inicial_y_politica(
    cliente: TestClient, dos_gerentes: DosGerentes, db: Session
) -> None:
    asistente = dos_gerentes.uno.asistente
    asistente.password_hash = hashear_contrasena(CLAVE)
    db.flush()

    r = cliente.get(PERFIL_URL, headers=auth(asistente))
    assert r.status_code == 200
    perfil = r.json()
    assert perfil["cambios_restantes"] == 2
    assert perfil["contrasena_inicial"] is True
    assert perfil["politica_vigente"] == politica.VERSION
    assert perfil["politica_version"] is None

    # CA07: el contador baja con cada cambio del mes.
    cambio = cliente.patch(
        "/api/v1/me/usuario", json={"username": "ana.nueva"}, headers=auth(asistente)
    )
    assert cambio.status_code == 200
    assert cliente.get(PERFIL_URL, headers=auth(asistente)).json()["cambios_restantes"] == 1

    # CA18: después de cambiarla deja de ser la contraseña inicial.
    sesion = cliente.post(
        "/api/v1/me/contrasena",
        json={"contrasena_actual": CLAVE, "contrasena_nueva": "Otra-Clave-2026"},
        headers=auth(asistente),
    )
    assert sesion.status_code == 200
    nuevo_token = sesion.json()["access_token"]
    renovado = cliente.get(PERFIL_URL, headers={"Authorization": f"Bearer {nuevo_token}"})
    assert renovado.json()["contrasena_inicial"] is False


@pytest.mark.parametrize("correo", ["", "   ", "ana@", "sin-arroba"])
def test_el_correo_que_llega_es_obligatorio_y_con_formato(
    cliente: TestClient, dos_gerentes: DosGerentes, correo: str
) -> None:
    """CA05. El mensaje lo pone el manejador común; el cliente valida antes con el suyo."""
    r = cliente.put(PERFIL_URL, json=datos(correo=correo), headers=auth(dos_gerentes.uno.gerente))
    assert r.status_code == 422
    assert r.json()["code"] == "VALIDACION"
    assert r.json()["field"] == "correo"


def test_sin_correo_en_la_solicitud_se_conserva_el_registrado(
    cliente: TestClient, dos_gerentes: DosGerentes, db: Session
) -> None:
    gerente = dos_gerentes.uno.gerente
    gerente.correo = "gerente@empresa.pe"
    db.flush()
    r = cliente.put(PERFIL_URL, json=datos(), headers=auth(gerente))
    assert r.status_code == 200
    assert r.json()["correo"] == "gerente@empresa.pe"


def test_la_politica_vigente_cumple_el_deber_de_informacion(
    cliente: TestClient, dos_gerentes: DosGerentes
) -> None:
    r = cliente.get(POLITICA_URL, headers=auth(dos_gerentes.uno.asistente))
    assert r.status_code == 200
    vigente = r.json()
    assert vigente["version"] == politica.VERSION
    titulos = [s["titulo"] for s in vigente["secciones"]]
    # Ley 29733 art. 18 y reglamento art. 6.1: responsable, finalidad, destinatarios,
    # decisiones automatizadas, obligatoriedad, conservación y derechos.
    for titulo in (
        "Quién trata tus datos",
        "Para qué los usamos",
        "Decisiones automatizadas",
        "Quién más los ve",
        "Qué datos son obligatorios",
        "Cuánto tiempo los conservamos",
        "Tus derechos",
    ):
        assert titulo in titulos
    texto = " ".join(p for s in vigente["secciones"] for p in s["parrafos"])
    assert "Ley 29733" in texto
    assert "Autoridad Nacional de Protección de Datos Personales" in texto


def test_la_politica_requiere_sesion(cliente: TestClient) -> None:
    assert cliente.get(POLITICA_URL).status_code == 401


def test_solo_se_acepta_la_version_vigente(cliente: TestClient, dos_gerentes: DosGerentes) -> None:
    gerente = dos_gerentes.uno.gerente
    vieja = cliente.post(POLITICA_URL, json={"version": "2000-01"}, headers=auth(gerente))
    assert vieja.status_code == 409
    assert vieja.json()["code"] == "POLITICA_DESACTUALIZADA"

    vigente = cliente.post(POLITICA_URL, json={"version": politica.VERSION}, headers=auth(gerente))
    assert vigente.status_code == 200
    assert vigente.json()["politica_version"] == politica.VERSION
    assert vigente.json()["politica_aceptada_en"] is not None


def test_la_politica_usa_el_contacto_configurado(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(politica.settings, "politica_correo", "privacidad@empresa.pe")
    monkeypatch.setattr(politica.settings, "politica_domicilio", "Av. Larco 123, Miraflores")
    texto = " ".join(p for s in politica.secciones() for p in s.parrafos)
    assert "escríbenos a privacidad@empresa.pe" in texto
    assert "con domicilio en Av. Larco 123, Miraflores" in texto
