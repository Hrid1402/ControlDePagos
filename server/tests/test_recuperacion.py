import hashlib
import logging
import secrets
import uuid
from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.eventos import Evento
from app.core.seguridad import crear_token, hashear_contrasena
from app.main import app
from app.models import Auditoria, HistorialContrasena, TokenRestablecimiento, Usuario
from app.services.acceso import MENSAJE_RECUPERACION_GENERICO
from tests.conftest import DosGerentes

SOLICITAR = "/api/v1/auth/recuperar-contrasena"
RESTABLECER = "/api/v1/auth/restablecer-contrasena"
LOGIN = "/api/v1/auth/login"
ME = "/api/v1/auth/me"
RENOVAR = "/api/v1/auth/renovar"
CAMBIAR_CONTRASENA = "/api/v1/me/contrasena"
RESTABLECER_POR_GERENTE = "/api/v1/asistentes/{}/restablecer-contrasena"
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


@pytest.fixture
def correos(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, str, str]]:
    """Correos que el servicio intentó enviar: (destinatario, asunto, cuerpo)."""
    enviados: list[tuple[str, str, str]] = []

    def capturar(destinatario: str, asunto: str, cuerpo: str) -> bool:
        enviados.append((destinatario, asunto, cuerpo))
        return True

    monkeypatch.setattr("app.services.acceso.enviar_correo", capturar)
    return enviados


def tokens(db: Session) -> list[TokenRestablecimiento]:
    return list(db.scalars(select(TokenRestablecimiento)).all())


def test_solicitar_recuperacion_por_usuario_crea_token_y_envia_un_correo(
    cliente: TestClient, db: Session, equipos: DosGerentes, correos: list[tuple[str, str, str]]
) -> None:
    gerente = equipos.uno.gerente
    r = cliente.post(SOLICITAR, json={"username": gerente.username})
    assert r.status_code == 200
    assert r.json() == {"detail": MENSAJE_RECUPERACION_GENERICO}

    [token_db] = tokens(db)
    assert token_db.usuario_id == gerente.id
    assert token_db.usado_en is None
    restante = token_db.expira_en - datetime.now(UTC)
    assert timedelta(minutes=29) < restante <= timedelta(minutes=30)
    [(destinatario, _, cuerpo)] = correos
    assert destinatario == gerente.correo
    [enlace] = [linea for linea in cuerpo.splitlines() if linea.startswith("http")]
    base, _, token = enlace.rpartition("/restablecer/")
    assert base == settings.url_cliente.rstrip("/")
    assert hashlib.sha256(token.encode()).hexdigest() == token_db.token_hash
    assert "30 minutos" in cuerpo


def test_solicitar_recuperacion_acepta_mayusculas_y_espacios(
    cliente: TestClient, db: Session, equipos: DosGerentes, correos: list[tuple[str, str, str]]
) -> None:
    gerente = equipos.uno.gerente
    r = cliente.post(SOLICITAR, json={"username": f"  {gerente.username.upper()}  "})
    assert r.status_code == 200
    assert [c[0] for c in correos] == [gerente.correo]
    assert len(tokens(db)) == 1


def sin_correo(usuario: Usuario) -> None:
    usuario.correo = None


def inactivo(usuario: Usuario) -> None:
    usuario.estado = "inactiva"


def eliminado(usuario: Usuario) -> None:
    usuario.eliminado_en = datetime.now(UTC)


@pytest.mark.parametrize("preparar", [None, inactivo, eliminado, sin_correo])
def test_solicitar_recuperacion_responde_igual_y_no_envia_si_no_puede(
    cliente: TestClient,
    db: Session,
    equipos: DosGerentes,
    correos: list[tuple[str, str, str]],
    preparar: Callable[[Usuario], None] | None,
) -> None:
    asistente = equipos.uno.asistente
    username = "nadie.existe" if preparar is None else asistente.username
    if preparar is not None:
        preparar(asistente)
        db.flush()
    valido = cliente.post(SOLICITAR, json={"username": equipos.uno.gerente.username})
    assert len(correos) == 1
    correos.clear()

    r = cliente.post(SOLICITAR, json={"username": username})
    assert r.status_code == valido.status_code == 200
    assert r.json() == valido.json()
    assert correos == []
    assert [t.usuario_id for t in tokens(db)] == [equipos.uno.gerente.id]


def test_solicitar_recuperacion_no_guarda_el_usuario_escrito(
    cliente: TestClient,
    db: Session,
    correos: list[tuple[str, str, str]],
    caplog: pytest.LogCaptureFixture,
) -> None:
    antes = db.scalar(select(func.count()).select_from(Auditoria))
    with caplog.at_level(logging.DEBUG):
        r = cliente.post(SOLICITAR, json={"username": "Secreto.Escrito"})
    assert r.status_code == 200
    assert "secreto.escrito" not in caplog.text.lower()
    assert db.scalar(select(func.count()).select_from(Auditoria)) == antes
    assert tokens(db) == []


@pytest.mark.parametrize("cuerpo", [{"correo": "nadie@example.com"}, {}, {"username": "ab"}])
def test_solicitar_recuperacion_valida_el_usuario(
    cliente: TestClient, cuerpo: dict[str, str]
) -> None:
    r = cliente.post(SOLICITAR, json=cuerpo)
    assert r.status_code == 422
    assert r.json()["code"] == "VALIDACION"
    assert r.json()["field"] == "username"


def test_un_fallo_de_envio_no_cambia_la_respuesta_ni_registra_datos(
    cliente: TestClient,
    db: Session,
    equipos: DosGerentes,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    gerente = equipos.uno.gerente
    assert gerente.correo is not None

    def servidor_caido(*_: object, **__: object) -> None:
        raise OSError(f"no se pudo entregar a {gerente.correo}")

    monkeypatch.setattr("app.core.email.smtplib.SMTP", servidor_caido)
    with caplog.at_level(logging.DEBUG):
        r = cliente.post(SOLICITAR, json={"username": gerente.username})
    assert r.status_code == 200
    assert r.json() == {"detail": MENSAJE_RECUPERACION_GENERICO}
    texto = caplog.text.lower()
    assert "no se envió el correo de recuperación" in texto
    assert gerente.username.lower() not in texto
    assert gerente.correo.lower() not in texto


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
        json={"token": "token-falso-inexistente", "nueva_contrasena": "NuevaClave123!"},
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
        json={"token": token_crudo, "nueva_contrasena": "NuevaClave123!"},
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
        json={"token": token_crudo, "nueva_contrasena": "NuevaClave123!"},
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


def test_el_enlace_del_correo_restablece_la_contrasena(
    cliente: TestClient, db: Session, equipos: DosGerentes, correos: list[tuple[str, str, str]]
) -> None:
    gerente = equipos.uno.gerente
    cliente.post(SOLICITAR, json={"username": gerente.username})
    [(_, _, cuerpo)] = correos
    token = next(
        linea.rpartition("/restablecer/")[2]
        for linea in cuerpo.splitlines()
        if "/restablecer/" in linea
    )
    r = cliente.post(RESTABLECER, json={"token": token, "nueva_contrasena": "Otra-clave-nueva-7"})
    assert r.status_code == 200
    r = cliente.post(RESTABLECER, json={"token": token, "nueva_contrasena": "Otra-clave-nueva-8"})
    assert r.status_code == 400
    assert r.json()["code"] == "TOKEN_INVALIDO"


# Estado de la cuenta y sesiones al restablecer (TASK-5)


def nuevo_token(db: Session, usuario: Usuario) -> tuple[str, TokenRestablecimiento]:
    crudo = secrets.token_urlsafe(32)
    registro = TokenRestablecimiento(
        usuario_id=usuario.id,
        token_hash=hashlib.sha256(crudo.encode()).hexdigest(),
        expira_en=datetime.now(UTC) + timedelta(minutes=30),
    )
    db.add(registro)
    db.commit()
    return crudo, registro


def pedir_enlace(cliente: TestClient, correos: list[tuple[str, str, str]], usuario: Usuario) -> str:
    """Pide la recuperación por la API y devuelve el token del enlace que llegó por correo."""
    assert cliente.post(SOLICITAR, json={"username": usuario.username}).status_code == 200
    _, _, cuerpo = correos[-1]
    return next(
        linea.rpartition("/restablecer/")[2]
        for linea in cuerpo.splitlines()
        if "/restablecer/" in linea
    )


def test_restablecer_desbloquea_la_cuenta_y_permite_ingresar_de_inmediato(
    cliente: TestClient, db: Session, equipos: DosGerentes
) -> None:
    asistente = equipos.uno.asistente
    asistente.intentos_fallidos = 5
    asistente.bloqueado_hasta = datetime.now(UTC) + timedelta(minutes=14)
    db.flush()
    assert (
        cliente.post(
            LOGIN, json={"username": asistente.username, "contrasena": CONTRASENA_INICIAL}
        ).json()["code"]
        == "CUENTA_BLOQUEADA"
    )
    token, _ = nuevo_token(db, asistente)

    r = cliente.post(RESTABLECER, json={"token": token, "nueva_contrasena": "Nueva-clave-1"})

    assert r.status_code == 200
    db.refresh(asistente)
    assert (asistente.intentos_fallidos, asistente.bloqueado_hasta) == (0, None)
    r = cliente.post(LOGIN, json={"username": asistente.username, "contrasena": "Nueva-clave-1"})
    assert r.status_code == 200


def test_la_sesion_abierta_antes_de_restablecer_queda_revocada(
    cliente: TestClient, db: Session, equipos: DosGerentes
) -> None:
    gerente = equipos.uno.gerente
    anterior = {"Authorization": f"Bearer {crear_token(gerente)}"}
    assert cliente.get(ME, headers=anterior).status_code == 200
    token, _ = nuevo_token(db, gerente)

    r = cliente.post(RESTABLECER, json={"token": token, "nueva_contrasena": "Nueva-clave-1"})

    assert r.status_code == 200
    for respuesta in (cliente.get(ME, headers=anterior), cliente.post(RENOVAR, headers=anterior)):
        assert (respuesta.status_code, respuesta.json()["code"]) == (401, "SESION_REVOCADA")


@pytest.mark.parametrize("preparar", [inactivo, eliminado])
def test_un_enlace_de_una_cuenta_desactivada_despues_no_sirve_ni_se_consume(
    cliente: TestClient,
    db: Session,
    equipos: DosGerentes,
    preparar: Callable[[Usuario], None],
) -> None:
    asistente = equipos.uno.asistente
    token, registro = nuevo_token(db, asistente)
    hash_previo, version_previa = asistente.password_hash, asistente.token_version
    preparar(asistente)
    db.flush()

    r = cliente.post(RESTABLECER, json={"token": token, "nueva_contrasena": "Nueva-clave-1"})

    assert (r.status_code, r.json()["code"]) == (400, "TOKEN_INVALIDO")
    db.refresh(registro)
    db.refresh(asistente)
    assert registro.usado_en is None
    assert (asistente.password_hash, asistente.token_version) == (hash_previo, version_previa)


def test_un_segundo_enlace_pedido_antes_de_restablecer_queda_invalido(
    cliente: TestClient, db: Session, equipos: DosGerentes, correos: list[tuple[str, str, str]]
) -> None:
    gerente = equipos.uno.gerente
    primero = pedir_enlace(cliente, correos, gerente)
    segundo = pedir_enlace(cliente, correos, gerente)

    r = cliente.post(RESTABLECER, json={"token": primero, "nueva_contrasena": "Nueva-clave-1"})
    assert r.status_code == 200

    r = cliente.post(RESTABLECER, json={"token": segundo, "nueva_contrasena": "Otra-clave-2"})
    assert (r.status_code, r.json()["code"]) == (400, "TOKEN_INVALIDO")
    assert all(t.usado_en is not None for t in tokens(db))
    r = cliente.post(LOGIN, json={"username": gerente.username, "contrasena": "Nueva-clave-1"})
    assert r.status_code == 200


def test_un_enlace_pedido_antes_de_cambiar_la_contrasena_en_mi_cuenta_queda_invalido(
    cliente: TestClient, db: Session, equipos: DosGerentes, correos: list[tuple[str, str, str]]
) -> None:
    asistente = equipos.uno.asistente
    pendiente = pedir_enlace(cliente, correos, asistente)

    r = cliente.post(
        CAMBIAR_CONTRASENA,
        json={"contrasena_actual": CONTRASENA_INICIAL, "contrasena_nueva": "Nueva-clave-1"},
        headers={"Authorization": f"Bearer {crear_token(asistente)}"},
    )
    assert r.status_code == 200, r.text

    r = cliente.post(RESTABLECER, json={"token": pendiente, "nueva_contrasena": "Otra-clave-2"})
    assert (r.status_code, r.json()["code"]) == (400, "TOKEN_INVALIDO")
    # Solo se invalidan los enlaces pedidos antes del cambio: uno nuevo sí funciona.
    nuevo = pedir_enlace(cliente, correos, asistente)
    r = cliente.post(RESTABLECER, json={"token": nuevo, "nueva_contrasena": "Otra-clave-2"})
    assert r.status_code == 200


def test_restablecer_no_invalida_los_enlaces_de_otra_cuenta(
    cliente: TestClient, db: Session, equipos: DosGerentes
) -> None:
    propio, _ = nuevo_token(db, equipos.uno.gerente)
    ajeno, registro_ajeno = nuevo_token(db, equipos.dos.gerente)

    r = cliente.post(RESTABLECER, json={"token": propio, "nueva_contrasena": "Nueva-clave-1"})

    assert r.status_code == 200
    db.refresh(registro_ajeno)
    assert registro_ajeno.usado_en is None
    r = cliente.post(RESTABLECER, json={"token": ajeno, "nueva_contrasena": "Nueva-clave-1"})
    assert r.status_code == 200


# Restablecimiento por el gerente: la salida de quien no tiene correo (H01, TASK-14)


def restablecer_por_gerente(cliente: TestClient, gerente: Usuario, asistente: Usuario) -> str:
    """Restablece la contraseña de la asistente desde la cuenta de su gerente y devuelve la
    contraseña generada, que la API muestra una sola vez."""
    r = cliente.post(
        RESTABLECER_POR_GERENTE.format(asistente.id),
        headers={"Authorization": f"Bearer {crear_token(gerente)}"},
    )
    assert r.status_code == 200, r.text
    contrasena: str = r.json()["contrasena"]
    return contrasena


def test_la_asistente_sin_correo_restablecida_por_su_gerente_ingresa_con_la_nueva(
    cliente: TestClient,
    db: Session,
    equipos: DosGerentes,
    correos: list[tuple[str, str, str]],
    publicados: list[tuple[uuid.UUID, Evento]],
) -> None:
    equipo = equipos.uno
    asistente = equipo.asistente
    asistente.correo = None
    db.flush()
    anterior = {"Authorization": f"Bearer {crear_token(asistente)}"}

    # Sin correo, la recuperación responde lo mismo de siempre y no crea ningún enlace: la
    # salida es pedirle al gerente que la restablezca.
    r = cliente.post(SOLICITAR, json={"username": asistente.username})
    assert r.json() == {"detail": MENSAJE_RECUPERACION_GENERICO}
    assert (tokens(db), correos) == ([], [])

    nueva = restablecer_por_gerente(cliente, equipo.gerente, asistente)

    r = cliente.post(LOGIN, json={"username": asistente.username, "contrasena": nueva})
    assert r.status_code == 200
    r = cliente.post(LOGIN, json={"username": asistente.username, "contrasena": CONTRASENA_INICIAL})
    assert (r.status_code, r.json()["code"]) == (401, "CREDENCIALES_INVALIDAS")
    r = cliente.get(ME, headers=anterior)
    assert (r.status_code, r.json()["code"]) == (401, "SESION_REVOCADA")


def test_un_enlace_pedido_antes_de_que_el_gerente_restablezca_queda_invalido(
    cliente: TestClient,
    db: Session,
    equipos: DosGerentes,
    correos: list[tuple[str, str, str]],
    publicados: list[tuple[uuid.UUID, Evento]],
) -> None:
    # Con correo, porque sin él no se crea enlace: este es el caso de quien pidió el enlace y
    # luego pidió ayuda al gerente.
    equipo = equipos.uno
    pendiente = pedir_enlace(cliente, correos, equipo.asistente)

    nueva = restablecer_por_gerente(cliente, equipo.gerente, equipo.asistente)

    r = cliente.post(RESTABLECER, json={"token": pendiente, "nueva_contrasena": "Otra-clave-2"})
    assert (r.status_code, r.json()["code"]) == (400, "TOKEN_INVALIDO")
    assert all(t.usado_en is not None for t in tokens(db))
    r = cliente.post(LOGIN, json={"username": equipo.asistente.username, "contrasena": nueva})
    assert r.status_code == 200
