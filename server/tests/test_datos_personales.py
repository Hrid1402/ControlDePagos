"""Pruebas de datos personales y cambios de cuenta (H02, TASK-10).

Completa lo que no cubren test_usuarios.py, test_cuenta.py y test_mi_cuenta_api.py: los bordes
de cada documento, la unicidad sin distinguir mayúsculas, los campos que el usuario no puede
tocar, la política versionada y la sugerencia de la contraseña inicial.
"""

from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencias import Origen
from app.core.politica import VERSION
from app.core.seguridad import crear_token, hashear_contrasena
from app.main import app
from app.models import Auditoria, Usuario
from app.services.asistentes import restablecer_contrasena_asistente
from tests.conftest import DosGerentes

PERFIL_URL = "/api/v1/usuarios/perfil"
POLITICA_URL = "/api/v1/usuarios/politica"
CONTRASENA_URL = "/api/v1/me/contrasena"
ORIGEN = Origen(dispositivo="pruebas", ip=None)
BASE = {"nombres": "Lucía", "apellidos": "Gómez Flores", "celular": "987654321"}


@pytest.fixture
def cliente(db: Session) -> Iterator[TestClient]:
    app.dependency_overrides[get_db] = lambda: db
    yield TestClient(app)
    app.dependency_overrides.pop(get_db, None)


def cabecera(usuario: Usuario) -> dict[str, str]:
    return {"Authorization": f"Bearer {crear_token(usuario)}"}


def guardar(cliente: TestClient, usuario: Usuario, **campos: Any) -> Any:
    return cliente.put(PERFIL_URL, json={**BASE, **campos}, headers=cabecera(usuario))


def campo_con_error(respuesta: Any) -> str | None:
    cuerpo = respuesta.json()
    return cuerpo.get("field")


@pytest.mark.parametrize(
    ("tipo", "numero"),
    [
        ("dni", "12345678"),
        ("ce", "A12345678"),
        ("ce", "ABCDEF123456"),
        ("pasaporte", "PE1234567"),
        ("pasaporte", "pe12345678ab"),
    ],
)
def test_ca02_ca03_documentos_validos(
    cliente: TestClient, dos_gerentes: DosGerentes, tipo: str, numero: str
) -> None:
    r = guardar(cliente, dos_gerentes.uno.gerente, tipo_documento=tipo, numero_documento=numero)
    assert r.status_code == 200, r.text
    assert r.json()["tipo_documento"] == tipo


@pytest.mark.parametrize(
    ("tipo", "numero"),
    [
        ("dni", "1234567"),
        ("dni", "123456789"),
        ("dni", "1234567A"),
        ("ce", "A1234567"),
        ("ce", "A123456789012"),
        ("pasaporte", "PE-123456"),
        ("pasaporte", "PE 1234567"),
        ("ruc", "20123456789"),
    ],
)
def test_ca02_ca03_documentos_invalidos_no_cambian_nada(
    cliente: TestClient, db: Session, dos_gerentes: DosGerentes, tipo: str, numero: str
) -> None:
    gerente = dos_gerentes.uno.gerente
    r = guardar(cliente, gerente, tipo_documento=tipo, numero_documento=numero)
    assert r.status_code == 422
    db.refresh(gerente)
    assert (gerente.tipo_documento, gerente.numero_documento, gerente.nombres) == (
        None,
        None,
        None,
    )


def test_ca03_numero_sin_tipo_se_rechaza(cliente: TestClient, dos_gerentes: DosGerentes) -> None:
    r = guardar(cliente, dos_gerentes.uno.gerente, numero_documento="12345678")
    assert r.status_code == 422


def test_ca04_el_mismo_documento_con_otras_mayusculas_esta_ocupado(
    cliente: TestClient, dos_gerentes: DosGerentes
) -> None:
    guardar(
        cliente,
        dos_gerentes.uno.gerente,
        tipo_documento="pasaporte",
        numero_documento="PE1234567",
    )

    r = guardar(
        cliente,
        dos_gerentes.dos.asistente,
        tipo_documento="pasaporte",
        numero_documento="pe1234567",
    )

    assert (r.status_code, r.json()["code"]) == (409, "DOCUMENTO_DUPLICADO")
    assert campo_con_error(r) == "numero_documento"


def test_ca04_ca05_volver_a_guardar_los_propios_datos_no_es_duplicado(
    cliente: TestClient, dos_gerentes: DosGerentes
) -> None:
    gerente = dos_gerentes.uno.gerente
    datos = {"tipo_documento": "ce", "numero_documento": "ABC123456", "correo": "ana@correo.pe"}
    assert guardar(cliente, gerente, **datos).status_code == 200

    otra_vez = guardar(cliente, gerente, **{**datos, "correo": "ANA@Correo.pe"})

    assert otra_vez.status_code == 200, otra_vez.text
    assert otra_vez.json()["numero_documento"] == "ABC123456"


def test_ca05_el_correo_duplicado_marca_su_campo(
    cliente: TestClient, dos_gerentes: DosGerentes
) -> None:
    guardar(cliente, dos_gerentes.uno.gerente, correo="compartido@correo.pe")
    r = guardar(cliente, dos_gerentes.uno.asistente, correo=" Compartido@Correo.PE ")
    assert (r.status_code, r.json()["code"]) == (409, "CORREO_DUPLICADO")
    assert campo_con_error(r) == "correo"


def test_ca09_ca11_los_campos_de_la_cuenta_no_se_editan_desde_el_perfil(
    cliente: TestClient, db: Session, dos_gerentes: DosGerentes
) -> None:
    asistente = dos_gerentes.uno.asistente
    antes = (
        asistente.id,
        asistente.username,
        asistente.rol,
        asistente.estado,
        asistente.gerente_id,
        asistente.token_version,
        asistente.contrasena_inicial,
    )

    r = guardar(
        cliente,
        asistente,
        id=str(dos_gerentes.dos.gerente.id),
        username="otro_usuario",
        rol="gerente",
        estado="inactiva",
        gerente_id=str(dos_gerentes.dos.gerente.id),
        token_version=99,
        contrasena_inicial=False,
    )

    assert r.status_code == 200
    db.refresh(asistente)
    assert (
        asistente.id,
        asistente.username,
        asistente.rol,
        asistente.estado,
        asistente.gerente_id,
        asistente.token_version,
        asistente.contrasena_inicial,
    ) == antes
    assert asistente.nombres == "Lucía"


def test_ca10_la_politica_no_se_acepta_desde_el_perfil(
    cliente: TestClient, db: Session, dos_gerentes: DosGerentes
) -> None:
    """Solo POST /politica registra la aceptación, y solo de la versión vigente."""
    gerente = dos_gerentes.uno.gerente

    r = guardar(cliente, gerente, politica_version="2000-01")

    assert r.status_code == 200
    assert (r.json()["politica_version"], r.json()["politica_aceptada_en"]) == (None, None)
    db.refresh(gerente)
    assert gerente.politica_version is None


def test_ca10_aceptar_la_vigente_guarda_version_y_fecha_una_vez_por_aceptacion(
    cliente: TestClient, db: Session, dos_gerentes: DosGerentes
) -> None:
    gerente = dos_gerentes.uno.gerente

    antigua = cliente.post(POLITICA_URL, json={"version": "2000-01"}, headers=cabecera(gerente))
    assert (antigua.status_code, antigua.json()["code"]) == (409, "POLITICA_DESACTUALIZADA")
    vigente = cliente.post(POLITICA_URL, json={"version": VERSION}, headers=cabecera(gerente))

    assert vigente.status_code == 200
    assert vigente.json()["politica_version"] == VERSION
    assert vigente.json()["politica_aceptada_en"] is not None
    assert cliente.get(PERFIL_URL, headers=cabecera(gerente)).json()["politica_vigente"] == VERSION
    aceptaciones = db.scalar(
        select(func.count())
        .select_from(Auditoria)
        .where(Auditoria.usuario_id == gerente.id, Auditoria.accion == "politica_aceptada")
    )
    assert aceptaciones == 1


def test_ca11_la_asistente_edita_sus_datos_sin_tocar_los_de_su_gerente(
    cliente: TestClient, db: Session, dos_gerentes: DosGerentes
) -> None:
    equipo = dos_gerentes.uno
    r = guardar(cliente, equipo.asistente, nombres="Rosa")

    assert r.json()["id"] == str(equipo.asistente.id)
    db.refresh(equipo.gerente)
    assert equipo.gerente.nombres is None


def test_ca17_el_token_anterior_ya_no_edita_el_perfil(
    cliente: TestClient, db: Session, dos_gerentes: DosGerentes
) -> None:
    gerente = dos_gerentes.uno.gerente
    gerente.password_hash = hashear_contrasena("Clave-actual-1")
    db.flush()
    anterior = cabecera(gerente)

    r = cliente.post(
        CONTRASENA_URL,
        json={"contrasena_actual": "Clave-actual-1", "contrasena_nueva": "Clave-nueva-2!"},
        headers=anterior,
    )
    assert r.status_code == 200, r.text
    renovado = {"Authorization": f"Bearer {r.json()['access_token']}"}

    assert cliente.put(PERFIL_URL, json=BASE, headers=anterior).status_code == 401
    assert cliente.put(PERFIL_URL, json=BASE, headers=renovado).status_code == 200


def test_ca18_la_sugerencia_vuelve_cuando_el_gerente_restablece_la_contrasena(
    cliente: TestClient, db: Session, dos_gerentes: DosGerentes
) -> None:
    equipo = dos_gerentes.uno
    equipo.asistente.contrasena_inicial = False
    db.flush()

    restablecer_contrasena_asistente(db, equipo.gerente, equipo.asistente.id, ORIGEN)
    db.refresh(equipo.asistente)

    perfil = cliente.get(PERFIL_URL, headers=cabecera(equipo.asistente)).json()
    assert perfil["contrasena_inicial"] is True
