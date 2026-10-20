from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.seguridad import crear_token, hashear_contrasena, leer_token, verificar_contrasena
from app.main import app
from app.models import Auditoria, CambioUsuario, HistorialContrasena, Usuario
from app.services import cuenta
from app.services.auditoria import Accion
from tests.conftest import DosGerentes

USUARIO_URL = "/api/v1/me/usuario"
CONTRASENA_URL = "/api/v1/me/contrasena"
LOGIN_URL = "/api/v1/auth/login"
SESION_URL = "/api/v1/auth/me"
IP = "203.0.113.20"
LIMA = ZoneInfo("America/Lima")

CONTRASENA = "Clave-segura-1"
NUEVA = "Otra-clave-2"
# bcrypt es lento a propósito: los hashes se calculan una sola vez para todo el módulo.
HASH = hashear_contrasena(CONTRASENA)
# Contraseñas que tuvo la cuenta, de la más antigua a la más reciente.
PASADAS = ["Pasada-uno-1", "Pasada-dos-2", "Pasada-tres-3", "Pasada-cuatro-4"]
HASHES_PASADOS = [hashear_contrasena(c) for c in PASADAS]


def auth_headers(usuario: Usuario) -> dict[str, str]:
    return {"Authorization": f"Bearer {crear_token(usuario)}"}


@pytest.fixture
def cliente(db: Session) -> Iterator[TestClient]:
    app.dependency_overrides[get_db] = lambda: db
    yield TestClient(app, client=(IP, 50000))
    app.dependency_overrides.pop(get_db, None)


@pytest.fixture
def equipos(db: Session, dos_gerentes: DosGerentes) -> DosGerentes:
    """Los dos gerentes y sus asistentes con la contraseña CONTRASENA."""
    for equipo in (dos_gerentes.uno, dos_gerentes.dos):
        equipo.gerente.password_hash = HASH
        equipo.asistente.password_hash = HASH
    db.flush()
    return dos_gerentes


def cambiar_usuario(
    cliente: TestClient, usuario: Usuario, nuevo: str, headers: dict[str, str] | None = None
):
    return cliente.patch(
        USUARIO_URL, json={"username": nuevo}, headers=headers or auth_headers(usuario)
    )


def cambiar_contrasena(
    cliente: TestClient,
    usuario: Usuario,
    actual: str = CONTRASENA,
    nueva: str = NUEVA,
    headers: dict[str, str] | None = None,
):
    return cliente.post(
        CONTRASENA_URL,
        json={"contrasena_actual": actual, "contrasena_nueva": nueva},
        headers=headers or auth_headers(usuario),
    )


def registrar_cambios(db: Session, usuario: Usuario, *cuando: datetime) -> None:
    for creado_en in cuando:
        db.add(CambioUsuario(usuario_id=usuario.id, anterior="a", nuevo="b", creado_en=creado_en))
    db.flush()


def cambios_hechos(db: Session, usuario: Usuario) -> int:
    return (
        db.scalar(
            select(func.count())
            .select_from(CambioUsuario)
            .where(CambioUsuario.usuario_id == usuario.id)
        )
        or 0
    )


def eventos_de(db: Session, usuario: Usuario, accion: Accion) -> list[Auditoria]:
    return list(
        db.scalars(
            select(Auditoria).where(
                Auditoria.usuario_id == usuario.id, Auditoria.accion == accion.value
            )
        )
    )


def fijar_ahora(monkeypatch: pytest.MonkeyPatch, ahora: datetime) -> None:
    monkeypatch.setattr(cuenta, "ahora_lima", lambda: ahora)


# CA07: el usuario se edita hasta 2 veces al mes, sin repetirse con otro.


def test_ca07_dos_cambios_en_el_mes_y_cuantos_quedan(
    cliente: TestClient, db: Session, equipos: DosGerentes
) -> None:
    gerente = equipos.uno.gerente
    headers = auth_headers(gerente)

    primero = cambiar_usuario(cliente, gerente, "nuevo_uno", headers)
    segundo = cambiar_usuario(cliente, gerente, "nuevo_dos", headers)

    assert primero.status_code == 200, primero.text
    assert primero.json()["username"] == "nuevo_uno"
    assert primero.json()["cambios_restantes"] == 1
    assert segundo.status_code == 200, segundo.text
    assert segundo.json()["cambios_restantes"] == 0
    assert gerente.username == "nuevo_dos"
    assert cambios_hechos(db, gerente) == 2


def test_ca07_el_tercer_cambio_del_mes_se_rechaza(
    cliente: TestClient, db: Session, equipos: DosGerentes
) -> None:
    gerente = equipos.uno.gerente
    headers = auth_headers(gerente)
    cambiar_usuario(cliente, gerente, "nuevo_uno", headers)
    cambiar_usuario(cliente, gerente, "nuevo_dos", headers)

    tercero = cambiar_usuario(cliente, gerente, "nuevo_tres", headers)

    assert tercero.status_code == 409
    assert tercero.json()["code"] == "LIMITE_EXCEDIDO"
    assert tercero.json()["field"] == "username"
    assert gerente.username == "nuevo_dos"
    assert cambios_hechos(db, gerente) == 2


def test_ca07_el_cambio_queda_registrado_con_el_usuario_anterior_y_el_nuevo(
    cliente: TestClient, db: Session, equipos: DosGerentes
) -> None:
    gerente = equipos.uno.gerente
    anterior = gerente.username

    cambiar_usuario(cliente, gerente, "nuevo_uno")

    [cambio] = db.scalars(select(CambioUsuario).where(CambioUsuario.usuario_id == gerente.id))
    assert (cambio.anterior, cambio.nuevo) == (anterior, "nuevo_uno")


@pytest.mark.parametrize("ocupado", ["asistente_dos", "ASISTENTE_DOS", "Asistente_Dos"])
def test_ca07_un_usuario_de_otra_cuenta_se_rechaza_sin_distinguir_mayusculas(
    cliente: TestClient, db: Session, equipos: DosGerentes, ocupado: str
) -> None:
    gerente = equipos.uno.gerente

    r = cambiar_usuario(cliente, gerente, ocupado)

    assert r.status_code == 409
    assert r.json()["code"] == "DUPLICADO"
    assert r.json()["field"] == "username"
    assert cambios_hechos(db, gerente) == 0


def test_ca07_el_usuario_de_una_cuenta_eliminada_sigue_ocupado(
    cliente: TestClient, db: Session, equipos: DosGerentes
) -> None:
    gerente = equipos.uno.gerente
    equipos.uno.asistente.eliminado_en = datetime.now(UTC)
    db.flush()

    r = cambiar_usuario(cliente, gerente, equipos.uno.asistente.username)

    assert r.status_code == 409
    assert r.json()["code"] == "DUPLICADO"


@pytest.mark.parametrize("nuevo", ["GERENTE_UNO", "Gerente_Uno", "gerente_uno"])
def test_ca07_cambiar_solo_las_mayusculas_es_el_mismo_usuario_y_no_gasta_un_cambio(
    cliente: TestClient, db: Session, equipos: DosGerentes, nuevo: str
) -> None:
    gerente = equipos.uno.gerente

    r = cambiar_usuario(cliente, gerente, nuevo)

    assert r.status_code == 422
    assert r.json()["code"] == "VALIDACION"
    assert r.json()["field"] == "username"
    assert gerente.username == "gerente_uno"
    assert cambios_hechos(db, gerente) == 0


@pytest.mark.parametrize(
    "nuevo", ["", "   ", "dos palabras", "a b", "ab", "x" * 31, "ñandu", "a@b.com"]
)
def test_ca07_un_usuario_con_espacios_internos_o_fuera_de_largo_se_rechaza(
    cliente: TestClient, db: Session, equipos: DosGerentes, nuevo: str
) -> None:
    gerente = equipos.uno.gerente

    r = cambiar_usuario(cliente, gerente, nuevo)

    assert r.status_code == 422
    assert r.json()["field"] == "username"
    assert cambios_hechos(db, gerente) == 0


def test_ca07_los_espacios_de_los_extremos_se_recortan(
    cliente: TestClient, equipos: DosGerentes
) -> None:
    gerente = equipos.uno.gerente

    r = cambiar_usuario(cliente, gerente, "  con_bordes  ")

    assert r.status_code == 200, r.text
    assert gerente.username == "con_bordes"


def test_ca07_los_cambios_de_otra_cuenta_no_cuentan(
    cliente: TestClient, db: Session, equipos: DosGerentes
) -> None:
    otro = equipos.dos.gerente
    registrar_cambios(db, otro, datetime.now(UTC), datetime.now(UTC))

    r = cambiar_usuario(cliente, equipos.uno.gerente, "nuevo_uno")

    assert r.status_code == 200, r.text
    assert r.json()["cambios_restantes"] == 1


def test_ca07_la_asistente_cambia_solo_su_propio_usuario(
    cliente: TestClient, db: Session, equipos: DosGerentes
) -> None:
    asistente = equipos.uno.asistente

    r = cambiar_usuario(cliente, asistente, "asistente_nueva")

    assert r.status_code == 200, r.text
    assert asistente.username == "asistente_nueva"
    assert equipos.uno.gerente.username == "gerente_uno"
    assert cambios_hechos(db, equipos.uno.gerente) == 0


def test_ca07_el_cambio_de_usuario_se_audita(
    cliente: TestClient, db: Session, equipos: DosGerentes
) -> None:
    gerente = equipos.uno.gerente

    cambiar_usuario(cliente, gerente, "nuevo_uno")

    [evento] = eventos_de(db, gerente, Accion.USUARIO_CAMBIADO)
    assert evento.detalle == {"username": {"anterior": "gerente_uno", "nuevo": "nuevo_uno"}}


def test_ca07_el_token_sigue_valido_tras_cambiar_el_usuario(
    cliente: TestClient, equipos: DosGerentes
) -> None:
    gerente = equipos.uno.gerente
    headers = auth_headers(gerente)

    cambiar_usuario(cliente, gerente, "nuevo_uno", headers)

    r = cliente.get(SESION_URL, headers=headers)
    assert r.status_code == 200, r.text


def test_ca07_sin_sesion_responde_no_autenticado(cliente: TestClient) -> None:
    r = cliente.patch(USUARIO_URL, json={"username": "nuevo_uno"})

    assert r.status_code == 401
    assert r.json()["code"] == "NO_AUTENTICADO"


# CA07: el mes se cuenta en hora de Lima, no en UTC.


@pytest.mark.parametrize(
    ("hechos", "ahora", "esperado"),
    [
        # Medianoche de Lima: lo del 30 de septiembre ya no cuenta el 1 de octubre.
        (
            [datetime(2026, 9, 30, 23, 59, 59, tzinfo=LIMA)] * 2,
            datetime(2026, 10, 1, 0, 0, 0, tzinfo=LIMA),
            2,
        ),
        # El primer instante del mes ya cuenta.
        (
            [datetime(2026, 10, 1, 0, 0, 0, tzinfo=LIMA)],
            datetime(2026, 10, 31, 23, 59, 59, tzinfo=LIMA),
            1,
        ),
        # 23:30 del 31 en Lima son las 04:30 del 1 de noviembre en UTC: sigue siendo octubre.
        (
            [datetime(2026, 10, 31, 23, 30, tzinfo=LIMA)] * 2,
            datetime(2026, 10, 31, 23, 59, 59, tzinfo=LIMA),
            0,
        ),
        # Pasada la medianoche de Lima, noviembre empieza con los dos cambios.
        (
            [datetime(2026, 10, 31, 23, 30, tzinfo=LIMA)] * 2,
            datetime(2026, 11, 1, 0, 0, 1, tzinfo=LIMA),
            2,
        ),
    ],
)
def test_ca07_el_mes_se_corta_a_la_medianoche_de_lima(
    db: Session, equipos: DosGerentes, hechos: list[datetime], ahora: datetime, esperado: int
) -> None:
    gerente = equipos.uno.gerente
    registrar_cambios(db, gerente, *hechos)

    assert cuenta.cambios_restantes(db, gerente, ahora) == esperado


def test_ca07_a_medianoche_de_lima_el_endpoint_renueva_los_cambios(
    cliente: TestClient,
    db: Session,
    equipos: DosGerentes,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gerente = equipos.uno.gerente
    registrar_cambios(db, gerente, *[datetime(2026, 10, 31, 23, 30, tzinfo=LIMA)] * 2)

    fijar_ahora(monkeypatch, datetime(2026, 10, 31, 23, 59, 59, tzinfo=LIMA))
    antes = cambiar_usuario(cliente, gerente, "nuevo_uno")
    fijar_ahora(monkeypatch, datetime(2026, 10, 31, 23, 59, 59, tzinfo=LIMA) + timedelta(seconds=1))
    despues = cambiar_usuario(cliente, gerente, "nuevo_uno")

    assert antes.status_code == 409
    assert antes.json()["code"] == "LIMITE_EXCEDIDO"
    assert despues.status_code == 200, despues.text
    # El reloj falso solo mueve al servicio: el cambio nuevo lo fecha la base con la hora real.
    assert gerente.username == "nuevo_uno"


# CA08: se avisa que el usuario nuevo es el que se usa para ingresar.


def test_ca08_avisa_y_el_usuario_nuevo_es_el_que_ingresa(
    cliente: TestClient, equipos: DosGerentes
) -> None:
    gerente = equipos.uno.gerente

    r = cambiar_usuario(cliente, gerente, "nuevo_uno")
    con_nuevo = cliente.post(LOGIN_URL, json={"username": "nuevo_uno", "contrasena": CONTRASENA})
    con_viejo = cliente.post(LOGIN_URL, json={"username": "gerente_uno", "contrasena": CONTRASENA})

    assert r.json()["aviso"] == cuenta.AVISO_USUARIO_NUEVO
    assert "nuevo usuario" in r.json()["aviso"]
    assert con_nuevo.status_code == 200, con_nuevo.text
    assert con_viejo.status_code == 401
    assert con_viejo.json()["code"] == "CREDENCIALES_INVALIDAS"


# CA12: para cambiar la contraseña se pide la actual.


def test_ca12_con_la_actual_correcta_cambia_la_contrasena(
    cliente: TestClient, equipos: DosGerentes
) -> None:
    gerente = equipos.uno.gerente

    r = cambiar_contrasena(cliente, gerente)

    assert r.status_code == 200, r.text
    assert verificar_contrasena(NUEVA, gerente.password_hash)
    assert not verificar_contrasena(CONTRASENA, gerente.password_hash)


def test_ca12_con_la_actual_incorrecta_no_cambia_nada(
    cliente: TestClient, db: Session, equipos: DosGerentes
) -> None:
    gerente = equipos.uno.gerente
    version = gerente.token_version

    r = cambiar_contrasena(cliente, gerente, actual="Incorrecta-9")

    assert r.status_code == 422
    assert r.json() == {
        "detail": "La contraseña actual no es correcta.",
        "code": "CONTRASENA_INCORRECTA",
        "field": "contrasena_actual",
    }
    assert gerente.password_hash == HASH
    assert gerente.token_version == version
    assert (
        db.scalar(select(HistorialContrasena).where(HistorialContrasena.usuario_id == gerente.id))
        is None
    )
    assert not eventos_de(db, gerente, Accion.CONTRASENA_CAMBIADA)


def test_ca12_sin_la_actual_responde_validacion_en_su_campo(
    cliente: TestClient, equipos: DosGerentes
) -> None:
    gerente = equipos.uno.gerente

    r = cliente.post(
        CONTRASENA_URL, json={"contrasena_nueva": NUEVA}, headers=auth_headers(gerente)
    )

    assert r.status_code == 422
    assert r.json()["code"] == "VALIDACION"
    assert r.json()["field"] == "contrasena_actual"


def test_ca12_equivocarse_varias_veces_no_bloquea_la_cuenta(
    cliente: TestClient, equipos: DosGerentes
) -> None:
    gerente = equipos.uno.gerente

    fallos = [cambiar_contrasena(cliente, gerente, actual=f"Incorrecta-{i}") for i in range(6)]
    acierto = cambiar_contrasena(cliente, gerente)

    assert all(f.status_code == 422 for f in fallos)
    assert acierto.status_code == 200, acierto.text
    assert gerente.intentos_fallidos == 0
    assert gerente.bloqueado_hasta is None


def test_ca12_una_contrasena_de_mas_de_72_bytes_se_rechaza_en_su_campo(
    cliente: TestClient, equipos: DosGerentes
) -> None:
    gerente = equipos.uno.gerente

    r = cambiar_contrasena(cliente, gerente, nueva="Aa1-" * 19)

    assert r.status_code == 422
    assert r.json()["field"] == "contrasena_nueva"
    assert gerente.password_hash == HASH


def test_ca12_una_contrasena_de_pocos_caracteres_pero_mas_de_72_bytes_se_rechaza(
    cliente: TestClient, equipos: DosGerentes
) -> None:
    gerente = equipos.uno.gerente

    r = cambiar_contrasena(cliente, gerente, nueva="Ññ1-" * 13)

    assert r.status_code == 422
    assert r.json()["field"] == "contrasena_nueva"
    assert gerente.password_hash == HASH


@pytest.mark.parametrize(
    "nueva", ["Aa1-aaa", "otra-clave-2", "OTRA-CLAVE-2", "Otra-clave", "OtraClave2"]
)
def test_ca13_la_nueva_exige_8_caracteres_mayuscula_minuscula_numero_y_simbolo(
    cliente: TestClient, equipos: DosGerentes, nueva: str
) -> None:
    gerente = equipos.uno.gerente

    r = cambiar_contrasena(cliente, gerente, nueva=nueva)

    assert r.status_code == 422
    assert r.json()["code"] == "VALIDACION"
    assert r.json()["field"] == "contrasena_nueva"
    assert gerente.password_hash == HASH
    assert gerente.token_version == 0


def test_ca12_cada_usuario_cambia_solo_su_propia_contrasena(
    cliente: TestClient, equipos: DosGerentes
) -> None:
    r = cambiar_contrasena(cliente, equipos.uno.asistente)

    assert r.status_code == 200, r.text
    assert verificar_contrasena(NUEVA, equipos.uno.asistente.password_hash)
    for otro in (equipos.uno.gerente, equipos.dos.gerente, equipos.dos.asistente):
        assert otro.password_hash == HASH


def test_ca12_sin_sesion_responde_no_autenticado(cliente: TestClient) -> None:
    r = cliente.post(
        CONTRASENA_URL, json={"contrasena_actual": CONTRASENA, "contrasena_nueva": NUEVA}
    )

    assert r.status_code == 401
    assert r.json()["code"] == "NO_AUTENTICADO"


# CA16: la nueva no puede ser igual a la actual ni a las últimas 3.


def con_historial(db: Session, usuario: Usuario) -> None:
    """La cuenta tuvo las contraseñas PASADAS, de la más antigua a la más reciente."""
    inicio = datetime(2026, 1, 1, tzinfo=UTC)
    for i, password_hash in enumerate(HASHES_PASADOS):
        db.add(
            HistorialContrasena(
                usuario_id=usuario.id,
                password_hash=password_hash,
                creado_en=inicio + timedelta(days=i),
            )
        )
    db.flush()


def test_ca16_la_nueva_no_puede_ser_igual_a_la_actual(
    cliente: TestClient, equipos: DosGerentes
) -> None:
    gerente = equipos.uno.gerente

    r = cambiar_contrasena(cliente, gerente, nueva=CONTRASENA)

    assert r.status_code == 422
    assert r.json()["code"] == "CONTRASENA_REPETIDA"
    assert r.json()["field"] == "contrasena_nueva"
    assert gerente.password_hash == HASH
    assert gerente.token_version == 0


@pytest.mark.parametrize("pasada", PASADAS[1:])
def test_ca16_la_nueva_no_puede_ser_ninguna_de_las_ultimas_3(
    cliente: TestClient, db: Session, equipos: DosGerentes, pasada: str
) -> None:
    gerente = equipos.uno.gerente
    con_historial(db, gerente)

    r = cambiar_contrasena(cliente, gerente, nueva=pasada)

    assert r.status_code == 422
    assert r.json()["code"] == "CONTRASENA_REPETIDA"
    assert gerente.password_hash == HASH


def test_ca16_una_anterior_a_las_ultimas_3_se_acepta(
    cliente: TestClient, db: Session, equipos: DosGerentes
) -> None:
    gerente = equipos.uno.gerente
    con_historial(db, gerente)

    r = cambiar_contrasena(cliente, gerente, nueva=PASADAS[0])

    assert r.status_code == 200, r.text
    assert verificar_contrasena(PASADAS[0], gerente.password_hash)


def test_ca16_la_contrasena_que_se_reemplaza_entra_al_historial(
    cliente: TestClient, db: Session, equipos: DosGerentes
) -> None:
    gerente = equipos.uno.gerente
    cambiar_contrasena(cliente, gerente)

    volver = cambiar_contrasena(cliente, gerente, actual=NUEVA, nueva=CONTRASENA)

    assert volver.status_code == 422
    assert volver.json()["code"] == "CONTRASENA_REPETIDA"
    [guardada] = db.scalars(
        select(HistorialContrasena).where(HistorialContrasena.usuario_id == gerente.id)
    )
    assert guardada.password_hash == HASH


def test_ca16_el_historial_de_otra_cuenta_no_cuenta(
    cliente: TestClient, db: Session, equipos: DosGerentes
) -> None:
    con_historial(db, equipos.dos.gerente)

    r = cambiar_contrasena(cliente, equipos.uno.gerente, nueva=PASADAS[3])

    assert r.status_code == 200, r.text


# CA17: al cambiar la contraseña se cierran las demás sesiones.


def test_ca17_el_token_anterior_queda_revocado_y_el_nuevo_sigue_la_sesion(
    cliente: TestClient, equipos: DosGerentes
) -> None:
    gerente = equipos.uno.gerente
    token_anterior = {"Authorization": f"Bearer {crear_token(gerente)}"}
    otra_sesion = {"Authorization": f"Bearer {crear_token(gerente)}"}

    r = cambiar_contrasena(cliente, gerente, headers=token_anterior)

    assert r.status_code == 200, r.text
    assert gerente.token_version == 1
    nuevo = r.json()["access_token"]
    assert leer_token(nuevo).token_version == 1
    assert r.json()["usuario"]["id"] == str(gerente.id)
    for revocado in (token_anterior, otra_sesion):
        rechazado = cliente.get(SESION_URL, headers=revocado)
        assert rechazado.status_code == 401
        assert rechazado.json()["code"] == "SESION_REVOCADA"
    vigente = cliente.get(SESION_URL, headers={"Authorization": f"Bearer {nuevo}"})
    assert vigente.status_code == 200, vigente.text


def test_ca17_las_sesiones_de_otras_cuentas_no_se_cierran(
    cliente: TestClient, equipos: DosGerentes
) -> None:
    ajenas = [equipos.uno.asistente, equipos.dos.gerente, equipos.dos.asistente]
    cabeceras = [auth_headers(u) for u in ajenas]

    cambiar_contrasena(cliente, equipos.uno.gerente)

    for cabecera in cabeceras:
        assert cliente.get(SESION_URL, headers=cabecera).status_code == 200


def test_ca17_ingresa_con_la_nueva_y_ya_no_con_la_anterior(
    cliente: TestClient, equipos: DosGerentes
) -> None:
    gerente = equipos.uno.gerente
    cambiar_contrasena(cliente, gerente)

    con_nueva = cliente.post(LOGIN_URL, json={"username": gerente.username, "contrasena": NUEVA})
    con_vieja = cliente.post(
        LOGIN_URL, json={"username": gerente.username, "contrasena": CONTRASENA}
    )

    assert con_nueva.status_code == 200, con_nueva.text
    assert con_vieja.status_code == 401


def test_ca17_deja_de_usar_la_contrasena_inicial(cliente: TestClient, equipos: DosGerentes) -> None:
    gerente = equipos.uno.gerente
    assert gerente.contrasena_inicial is True

    cambiar_contrasena(cliente, gerente)

    assert gerente.contrasena_inicial is False


def test_ca17_la_auditoria_registra_el_cambio_sin_contrasenas_ni_hashes(
    cliente: TestClient, db: Session, equipos: DosGerentes
) -> None:
    gerente = equipos.uno.gerente

    cambiar_contrasena(cliente, gerente)

    [evento] = eventos_de(db, gerente, Accion.CONTRASENA_CAMBIADA)
    assert evento.detalle == {"token_version": {"anterior": 0, "nuevo": 1}}
    texto = str(evento.detalle)
    assert NUEVA not in texto and CONTRASENA not in texto and "$2b$" not in texto
