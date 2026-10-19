import logging
import uuid
from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from ipaddress import IPv4Address, IPv6Address, ip_address
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel
from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencias import Origen, OrigenSolicitud, SesionDb, UsuarioActual
from app.core.errores import ErrorApi, registrar_manejadores
from app.core.paginacion import ParametrosPagina, paginar
from app.core.seguridad import crear_token
from app.models import Auditoria, Usuario
from app.models.acceso import AuditoriaInmutable
from app.services.auditoria import (
    Accion,
    consulta_historial,
    diferencias,
    registrar_auditoria,
    registrar_login_desconocido,
)
from tests.conftest import DosGerentes

ORIGEN = Origen(dispositivo="Mozilla/5.0 (Android 14)", ip=ip_address("203.0.113.7"))

prueba = FastAPI()
registrar_manejadores(prueba)


@prueba.get("/origen")
def ver_origen(origen: OrigenSolicitud) -> dict[str, str | None]:
    return {"dispositivo": origen.dispositivo, "ip": None if origen.ip is None else str(origen.ip)}


class Ingreso(BaseModel):
    username: str
    password: str


@prueba.post("/login")
def login_desconocido(_: Ingreso, origen: OrigenSolicitud) -> None:
    registrar_login_desconocido(origen)
    raise ErrorApi(401, "CREDENCIALES_INVALIDAS", "Usuario o contraseña incorrectos.")


@prueba.get("/historial")
def historial(usuario: UsuarioActual, db: SesionDb, pagina: ParametrosPagina) -> dict[str, Any]:
    resultado = paginar(db, consulta_historial(usuario), pagina)
    return {"ids": [str(r.id) for r in resultado.items], "total": resultado.total}


@pytest.fixture
def cliente(db: Session) -> Iterator[TestClient]:
    prueba.dependency_overrides[get_db] = lambda: db
    yield TestClient(prueba, client=("203.0.113.7", 50000))
    prueba.dependency_overrides.clear()


def cabecera(usuario: Usuario) -> dict[str, str]:
    return {"Authorization": f"Bearer {crear_token(usuario)}"}


def contar(db: Session) -> int:
    return db.scalar(select(func.count()).select_from(Auditoria)) or 0


def releer(db: Session, registro: Auditoria) -> Auditoria:
    """Vuelve a leer el registro desde la base, no desde la sesión."""
    db.expire_all()
    leido = db.get(Auditoria, registro.id)
    assert leido is not None
    return leido


def auditar(db: Session, usuario: Usuario, detalle: dict[str, Any] | None = None) -> Auditoria:
    return registrar_auditoria(
        db, usuario, Accion.LOGIN_EXITOSO, "usuario", usuario.id, detalle, origen=ORIGEN
    )


# CA01: quién, qué, cuándo y desde qué dispositivo


def test_registra_quien_que_cuando_y_desde_donde(db: Session, dos_gerentes: DosGerentes) -> None:
    gerente = dos_gerentes.uno.gerente
    registro = releer(db, auditar(db, gerente, {"motivo": "prueba"}))
    assert registro.gerente_id == gerente.id
    assert registro.usuario_id == gerente.id
    assert registro.usuario_nombre == "gerente_uno"
    assert registro.accion == "login_exitoso"
    assert registro.entidad == "usuario"
    assert registro.entidad_id == gerente.id
    assert registro.detalle == {"motivo": "prueba"}
    assert registro.dispositivo == "Mozilla/5.0 (Android 14)"
    assert registro.creado_en is not None
    assert registro.creado_en.tzinfo is not None


def test_la_ip_se_lee_con_su_tipo(db: Session, dos_gerentes: DosGerentes) -> None:
    gerente = dos_gerentes.uno.gerente
    v4 = releer(db, auditar(db, gerente))
    assert isinstance(v4.ip, IPv4Address)
    assert v4.ip == IPv4Address("203.0.113.7")
    origen_v6 = Origen(dispositivo=None, ip=ip_address("2001:db8::1"))
    v6 = registrar_auditoria(
        db, gerente, Accion.LOGIN_EXITOSO, "usuario", gerente.id, origen=origen_v6
    )
    v6 = releer(db, v6)
    assert isinstance(v6.ip, IPv6Address)
    assert v6.ip == IPv6Address("2001:db8::1")


def test_sin_detalle_guarda_un_objeto_vacio(db: Session, dos_gerentes: DosGerentes) -> None:
    assert releer(db, auditar(db, dos_gerentes.uno.gerente)).detalle == {}


def test_un_registro_por_llamada(db: Session, dos_gerentes: DosGerentes) -> None:
    antes = contar(db)
    auditar(db, dos_gerentes.uno.gerente)
    assert contar(db) == antes + 1


# Gerente y usuario de cada evento


def test_el_evento_de_la_asistente_es_de_su_gerente(db: Session, dos_gerentes: DosGerentes) -> None:
    for equipo in (dos_gerentes.uno, dos_gerentes.dos):
        registro = releer(db, auditar(db, equipo.asistente))
        assert registro.gerente_id == equipo.gerente.id
        assert registro.usuario_id == equipo.asistente.id


def test_login_fallido_de_cuenta_conocida_registra_gerente_y_usuario(
    db: Session, dos_gerentes: DosGerentes
) -> None:
    asistente = dos_gerentes.dos.asistente
    registro = registrar_auditoria(
        db,
        asistente,
        Accion.LOGIN_FALLIDO,
        "usuario",
        asistente.id,
        {"intentos_fallidos": 1},
        origen=ORIGEN,
    )
    registro = releer(db, registro)
    assert registro.accion == "login_fallido"
    assert registro.gerente_id == dos_gerentes.dos.gerente.id
    assert registro.usuario_id == asistente.id


def test_asistente_sin_gerente_no_se_audita(db: Session) -> None:
    huerfana = Usuario(id=uuid.uuid4(), rol="asistente", username="huerfana", password_hash="x")
    with pytest.raises(ValueError, match="sin gerente"):
        auditar(db, huerfana)


# Nombre del usuario


def test_usa_nombres_y_apellidos_cuando_existen_ambos(
    db: Session, dos_gerentes: DosGerentes
) -> None:
    asistente = dos_gerentes.uno.asistente
    asistente.nombres = "María"
    asistente.apellidos = "Quispe Rojas"
    assert auditar(db, asistente).usuario_nombre == "María Quispe Rojas"


@pytest.mark.parametrize(
    ("nombres", "apellidos"),
    [(None, None), ("María", None), (None, "Quispe"), ("  ", "Quispe")],
)
def test_usa_el_username_si_falta_nombres_o_apellidos(
    db: Session, dos_gerentes: DosGerentes, nombres: str | None, apellidos: str | None
) -> None:
    asistente = dos_gerentes.uno.asistente
    asistente.nombres = nombres
    asistente.apellidos = apellidos
    assert auditar(db, asistente).usuario_nombre == "asistente_uno"


def test_conserva_el_nombre_si_se_elimina_la_cuenta(db: Session, dos_gerentes: DosGerentes) -> None:
    asistente = dos_gerentes.uno.asistente
    registro = auditar(db, asistente)
    db.execute(delete(Usuario).where(Usuario.id == asistente.id))
    registro = releer(db, registro)
    assert registro.usuario_id is None
    assert registro.usuario_nombre == "asistente_uno"
    assert registro.gerente_id == dos_gerentes.uno.gerente.id


# Sin secretos y con valores exactos


def test_el_detalle_no_guarda_secretos(db: Session, dos_gerentes: DosGerentes) -> None:
    detalle = {
        "password": "Secreta123",
        "password_hash": "$2b$12$abc",
        "contrasena_nueva": "Otra456",
        "access_token": "eyJ...",
        "token_hash": "abc",
        "jwt_secret": "clave",
        "clave_api": "k",
        "api_key": "k",
        "usuario": {"username": "maria", "Contraseña": "x", "tokens": ["a"]},
        "intentos": [{"refresh_token": "r", "ip": "203.0.113.7"}],
    }
    registro = releer(db, auditar(db, dos_gerentes.uno.gerente, detalle))
    assert registro.detalle == {
        "usuario": {"username": "maria"},
        "intentos": [{"ip": "203.0.113.7"}],
    }


def test_el_detalle_conserva_token_version(db: Session, dos_gerentes: DosGerentes) -> None:
    detalle = {"token_version": 3, "token": "eyJ..."}
    registro = releer(db, auditar(db, dos_gerentes.uno.gerente, detalle))
    assert registro.detalle == {"token_version": 3}


def test_el_detalle_guarda_montos_ids_y_fechas_exactos(
    db: Session, dos_gerentes: DosGerentes
) -> None:
    deuda_id = uuid.uuid4()
    detalle = {
        "monto": Decimal("1234.50"),
        "deuda_id": deuda_id,
        "vencimiento": date(2026, 10, 31),
        "pagado_en": datetime(2026, 10, 19, 15, 30, tzinfo=UTC),
        "activa": True,
        "cuota": 2,
        "moneda": "PEN",
        "nota": None,
        "periodos": ("2026-09", "2026-10"),
    }
    registro = releer(db, auditar(db, dos_gerentes.uno.gerente, detalle))
    assert registro.detalle == {
        "monto": "1234.50",
        "deuda_id": str(deuda_id),
        "vencimiento": "2026-10-31",
        "pagado_en": "2026-10-19T15:30:00+00:00",
        "activa": True,
        "cuota": 2,
        "moneda": "PEN",
        "nota": None,
        "periodos": ["2026-09", "2026-10"],
    }


@pytest.mark.parametrize("detalle", [{"monto": 10.5}, {"archivo": b"bytes"}, {1: "clave"}])
def test_el_detalle_rechaza_valores_no_previstos(
    db: Session, dos_gerentes: DosGerentes, detalle: dict[Any, Any]
) -> None:
    antes = contar(db)
    with pytest.raises(TypeError):
        auditar(db, dos_gerentes.uno.gerente, detalle)
    assert contar(db) == antes


def test_diferencias_devuelve_solo_lo_que_cambio() -> None:
    anterior = {"monto": Decimal("100.00"), "estado": "pendiente", "moneda": "PEN"}
    nuevo = {"monto": Decimal("120.00"), "estado": "pendiente", "moneda": "PEN", "nota": "ok"}
    assert diferencias(anterior, nuevo) == {
        "monto": {"anterior": "100.00", "nuevo": "120.00"},
        "nota": {"anterior": None, "nuevo": "ok"},
    }


def test_diferencias_omite_secretos_y_conserva_token_version() -> None:
    anterior = {"password_hash": "$2b$viejo", "token_version": 1}
    nuevo = {"password_hash": "$2b$nuevo", "token_version": 2}
    assert diferencias(anterior, nuevo) == {"token_version": {"anterior": 1, "nuevo": 2}}


# Misma transacción que la acción auditada


def test_si_la_accion_se_deshace_el_evento_tambien(db: Session, dos_gerentes: DosGerentes) -> None:
    asistente = dos_gerentes.uno.asistente
    antes = contar(db)
    accion = db.begin_nested()
    asistente.estado = "inactiva"
    registrar_auditoria(
        db,
        dos_gerentes.uno.gerente,
        Accion.CUENTA_DESACTIVADA,
        "usuario",
        asistente.id,
        {"cambios": diferencias({"estado": "activa"}, {"estado": "inactiva"})},
        origen=ORIGEN,
    )
    accion.rollback()
    assert contar(db) == antes
    db.refresh(asistente)
    assert asistente.estado == "activa"


# CA04: los registros no se editan ni se borran


def test_no_se_edita_un_registro(db: Session, dos_gerentes: DosGerentes) -> None:
    registro = auditar(db, dos_gerentes.uno.gerente)
    registro.accion = "otra_accion"
    with pytest.raises(AuditoriaInmutable, match="solo admite inserciones"):
        db.flush()


def test_no_se_borra_un_registro(db: Session, dos_gerentes: DosGerentes) -> None:
    registro = auditar(db, dos_gerentes.uno.gerente)
    db.delete(registro)
    with pytest.raises(AuditoriaInmutable):
        db.flush()


@pytest.mark.parametrize(
    "sentencia",
    [update(Auditoria).values(accion="otra_accion"), delete(Auditoria)],
    ids=["update", "delete"],
)
def test_no_se_edita_ni_borra_en_bloque(
    db: Session, dos_gerentes: DosGerentes, sentencia: Any
) -> None:
    auditar(db, dos_gerentes.uno.gerente)
    with pytest.raises(AuditoriaInmutable):
        db.execute(sentencia)


# Origen de la solicitud


def test_el_origen_lee_user_agent_e_ip(cliente: TestClient) -> None:
    r = cliente.get("/origen", headers={"User-Agent": "Mozilla/5.0 (iPhone)"})
    assert r.json() == {"dispositivo": "Mozilla/5.0 (iPhone)", "ip": "203.0.113.7"}


def test_el_origen_recorta_un_user_agent_largo(cliente: TestClient) -> None:
    r = cliente.get("/origen", headers={"User-Agent": "x" * 1000})
    assert r.json()["dispositivo"] == "x" * 300


def test_el_origen_sin_user_agent_queda_vacio(db: Session) -> None:
    with TestClient(prueba, headers={"User-Agent": ""}) as cliente:
        assert cliente.get("/origen").json()["dispositivo"] is None


def test_un_host_que_no_es_ip_no_se_guarda() -> None:
    # El TestClient por defecto se presenta como "testclient", que no cabe en inet.
    with TestClient(prueba) as cliente:
        assert cliente.get("/origen").json()["ip"] is None


# Ingreso con una cuenta desconocida: registro técnico


@pytest.fixture
def registro_tecnico(caplog: pytest.LogCaptureFixture) -> Iterator[pytest.LogCaptureFixture]:
    with caplog.at_level(logging.WARNING, logger="app.auditoria"):
        yield caplog


def eventos_tecnicos(caplog: pytest.LogCaptureFixture) -> list[logging.LogRecord]:
    return [r for r in caplog.records if r.name == "app.auditoria"]


def test_login_desconocido_va_al_registro_tecnico(
    cliente: TestClient, db: Session, registro_tecnico: pytest.LogCaptureFixture
) -> None:
    antes = contar(db)
    r = cliente.post(
        "/login",
        json={"username": "MiClaveSecreta99", "password": "OtraClave123"},
        headers={"User-Agent": "Mozilla/5.0 (Android 14)"},
    )
    assert r.status_code == 401
    assert contar(db) == antes
    eventos = eventos_tecnicos(registro_tecnico)
    assert len(eventos) == 1
    assert eventos[0].levelno == logging.WARNING
    assert getattr(eventos[0], "evento", None) == "login_desconocido"
    assert "203.0.113.7" in registro_tecnico.text
    assert "Mozilla/5.0 (Android 14)" in registro_tecnico.text
    assert "MiClaveSecreta99" not in registro_tecnico.text
    assert "OtraClave123" not in registro_tecnico.text


def test_login_desconocido_quita_saltos_de_linea(
    cliente: TestClient, registro_tecnico: pytest.LogCaptureFixture
) -> None:
    cliente.post(
        "/login",
        json={"username": "nadie", "password": "x"},
        headers={"User-Agent": "agente\r\nfalso: evento"},
    )
    mensaje = eventos_tecnicos(registro_tecnico)[0].getMessage()
    assert "\n" not in mensaje
    assert "\r" not in mensaje
    # Se quitan, no solo se escapan: tampoco queda la forma \r\n que dejaría %r.
    assert "\\r" not in mensaje
    assert "\\n" not in mensaje
    assert "'agentefalso: evento'" in mensaje


# Lectura autorizada: solo el gerente y solo lo suyo


def test_el_gerente_ve_lo_suyo_y_de_su_asistente_y_no_lo_ajeno(
    cliente: TestClient, db: Session, dos_gerentes: DosGerentes
) -> None:
    uno = [auditar(db, dos_gerentes.uno.gerente), auditar(db, dos_gerentes.uno.asistente)]
    dos = [auditar(db, dos_gerentes.dos.gerente), auditar(db, dos_gerentes.dos.asistente)]
    for equipo, propios, ajenos in ((dos_gerentes.uno, uno, dos), (dos_gerentes.dos, dos, uno)):
        cuerpo = cliente.get("/historial", headers=cabecera(equipo.gerente)).json()
        ids = set(cuerpo["ids"])
        assert {str(r.id) for r in propios} <= ids
        assert not {str(r.id) for r in ajenos} & ids
        total = db.scalar(
            select(func.count())
            .select_from(Auditoria)
            .where(Auditoria.gerente_id == equipo.gerente.id)
        )
        assert cuerpo["total"] == total


def test_el_historial_va_del_mas_reciente_al_mas_antiguo(
    db: Session, dos_gerentes: DosGerentes
) -> None:
    gerente = dos_gerentes.uno.gerente
    ahora = datetime.now(UTC)
    # Se insertan al revés de su fecha para comprobar que manda creado_en y no el id.
    nuevo = Auditoria(
        gerente_id=gerente.id,
        usuario_id=gerente.id,
        usuario_nombre="gerente_uno",
        accion="login_exitoso",
        entidad="usuario",
        creado_en=ahora + timedelta(days=1),
    )
    viejo = Auditoria(
        gerente_id=gerente.id,
        usuario_id=gerente.id,
        usuario_nombre="gerente_uno",
        accion="login_exitoso",
        entidad="usuario",
        creado_en=ahora - timedelta(days=1),
    )
    db.add_all([nuevo, viejo])
    db.flush()
    ids = [r.id for r in db.scalars(consulta_historial(gerente))]
    assert ids.index(nuevo.id) < ids.index(viejo.id)
    assert ids[0] == nuevo.id
    assert ids[-1] == viejo.id


def test_la_asistente_no_ve_el_historial_global(
    cliente: TestClient, db: Session, dos_gerentes: DosGerentes
) -> None:
    auditar(db, dos_gerentes.uno.gerente)
    for asistente in (dos_gerentes.uno.asistente, dos_gerentes.dos.asistente):
        r = cliente.get("/historial", headers=cabecera(asistente))
        assert r.status_code == 403
        assert r.json() == {
            "detail": "No tienes permiso para realizar esta acción.",
            "code": "SIN_PERMISO",
            "field": None,
        }


def test_el_historial_exige_sesion(cliente: TestClient) -> None:
    r = cliente.get("/historial")
    assert r.status_code == 401
    assert r.json()["code"] == "NO_AUTENTICADO"
