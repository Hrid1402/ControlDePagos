import concurrent.futures
import uuid
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import SessionLocal, get_db
from app.core.seguridad import crear_token, verificar_contrasena
from app.main import app
from app.models import Auditoria, HistorialContrasena, Usuario
from tests.conftest import DosGerentes

ASISTENTES_URL = "/api/v1/asistentes"
DISPONIBILIDAD_URL = "/api/v1/asistentes/disponibilidad"
LOGIN_URL = "/api/v1/auth/login"
IP = "203.0.113.12"


def auth_headers(usuario: Usuario) -> dict[str, str]:
    return {"Authorization": f"Bearer {crear_token(usuario)}"}


@pytest.fixture
def cliente(db: Session) -> Iterator[TestClient]:
    app.dependency_overrides[get_db] = lambda: db
    yield TestClient(app, client=(IP, 50000))
    app.dependency_overrides.pop(get_db, None)


def test_ca04_crear_asistente_solo_nombres_y_apellidos(
    cliente: TestClient,
    dos_gerentes: DosGerentes,
    db: Session,
) -> None:
    """CA04: Solo nombres y apellidos requeridos; credenciales generadas automáticamente."""
    gerente = dos_gerentes.uno.gerente
    payload = {
        "nombres": "Lucía Mariana",
        "apellidos": "Gómez Flores",
    }
    r = cliente.post(ASISTENTES_URL, json=payload, headers=auth_headers(gerente))
    assert r.status_code == 201, r.text
    data = r.json()

    assert data["nombres"] == "Lucía Mariana"
    assert data["apellidos"] == "Gómez Flores"
    assert "lucia.gomez" in data["username"].lower()
    assert len(data["contrasena"]) >= 12
    assert data["contrasena_inicial"] is True
    assert data["estado"] == "activa"

    # Verificar que los datos complementarios queden vacíos para que los llene la asistente
    asistente = db.get(Usuario, data["id"])
    assert asistente is not None
    assert asistente.correo is None
    assert asistente.celular is None
    assert asistente.numero_documento is None
    assert asistente.tipo_documento is None
    assert asistente.gerente_id == gerente.id
    assert asistente.rol == "asistente"


def test_ca08_credenciales_mostradas_una_sola_vez_y_login_exitoso(
    cliente: TestClient,
    dos_gerentes: DosGerentes,
    db: Session,
) -> None:
    """CA08: Credenciales en texto plano retornadas al crear, no en logs/BD, y funcionales."""
    gerente = dos_gerentes.uno.gerente
    payload = {
        "nombres": "Rosa",
        "apellidos": "Melgar",
    }
    r = cliente.post(ASISTENTES_URL, json=payload, headers=auth_headers(gerente))
    assert r.status_code == 201
    data = r.json()
    contrasena_plana = data["contrasena"]
    username = data["username"]

    # 1. En la BD no se guarda la contraseña plana
    asistente = db.get(Usuario, data["id"])
    assert asistente is not None
    assert asistente.password_hash != contrasena_plana
    assert verificar_contrasena(contrasena_plana, asistente.password_hash)

    # 2. La cuenta nueva todavía no tiene contraseñas anteriores
    historial = db.scalars(
        select(HistorialContrasena).where(HistorialContrasena.usuario_id == asistente.id)
    ).all()
    assert historial == []

    # 3. La contraseña no figura en ningún detalle de auditoría
    eventos = db.scalars(select(Auditoria).where(Auditoria.entidad_id == asistente.id)).all()
    for ev in eventos:
        assert contrasena_plana not in str(ev.detalle)

    # 4. Iniciar sesión con las credenciales generadas funciona
    r_login = cliente.post(
        LOGIN_URL,
        json={"username": username, "contrasena": contrasena_plana},
    )
    assert r_login.status_code == 200
    token_asistente = r_login.json()["access_token"]

    # 5. Consultar perfil con el nuevo token no expone la contraseña
    r_perfil = cliente.get(
        "/api/v1/usuarios/perfil",
        headers={"Authorization": f"Bearer {token_asistente}"},
    )
    assert r_perfil.status_code == 200
    assert "contrasena" not in r_perfil.json()


def test_creacion_con_credenciales_elegidas(
    cliente: TestClient,
    dos_gerentes: DosGerentes,
    db: Session,
) -> None:
    """Permite especificar usuario y contraseña personalizados."""
    gerente = dos_gerentes.uno.gerente
    payload = {
        "nombres": "Elena",
        "apellidos": "Paz",
        "username": "elena.paz.2026",
        "contrasena": "MiClaveSegura2026!",
    }
    r = cliente.post(ASISTENTES_URL, json=payload, headers=auth_headers(gerente))
    assert r.status_code == 201
    data = r.json()
    assert data["username"] == "elena.paz.2026"
    assert data["contrasena"] == "MiClaveSegura2026!"

    # Login con las credenciales elegidas
    r_login = cliente.post(
        LOGIN_URL,
        json={"username": "elena.paz.2026", "contrasena": "MiClaveSegura2026!"},
    )
    assert r_login.status_code == 200


def test_disponibilidad_de_username(cliente: TestClient, dos_gerentes: DosGerentes) -> None:
    """Verifica disponibilidad y sugerencias de username."""
    gerente = dos_gerentes.uno.gerente
    headers = auth_headers(gerente)

    # Username disponible
    r1 = cliente.get(f"{DISPONIBILIDAD_URL}?username=usuario_disponible_xyz", headers=headers)
    assert r1.status_code == 200
    data1 = r1.json()
    assert data1["disponible"] is True
    assert data1["sugerencia"] is None

    # Username ocupado (usar el de un gerente existente)
    r2 = cliente.get(f"{DISPONIBILIDAD_URL}?username={gerente.username}", headers=headers)
    assert r2.status_code == 200
    data2 = r2.json()
    assert data2["disponible"] is False
    assert data2["sugerencia"] is not None
    assert gerente.username in data2["sugerencia"]


def test_rechazo_username_duplicado(cliente: TestClient, dos_gerentes: DosGerentes) -> None:
    """Rechaza la creación si el username ya está ocupado con código 409."""
    gerente = dos_gerentes.uno.gerente
    payload = {
        "nombres": "Patricia",
        "apellidos": "Silva",
        "username": gerente.username.upper(),  # Prueba insensibilidad a mayúsculas
    }
    r = cliente.post(ASISTENTES_URL, json=payload, headers=auth_headers(gerente))
    assert r.status_code == 409
    assert r.json()["code"] == "USERNAME_DUPLICADO"


@pytest.mark.parametrize(
    "contrasena_invalida",
    [
        "corta",  # 5 caracteres
        "1234567",  # 7 caracteres
        "sinmayuscula-1",
        "SINMINUSCULA-1",
        "Sin-numero",
        "SinSimbolo1",
        "Ññ1-" * 13,  # 52 caracteres, 78 bytes: bcrypt no la admite
    ],
)
def test_politica_contrasena_segura(
    cliente: TestClient,
    dos_gerentes: DosGerentes,
    db: Session,
    contrasena_invalida: str,
) -> None:
    """Rechaza con 422 las contraseñas que no cumplen H02 CA13 o superan 72 bytes."""
    gerente = dos_gerentes.uno.gerente
    payload = {
        "nombres": "Lorena",
        "apellidos": "Quispe",
        "contrasena": contrasena_invalida,
    }
    r = cliente.post(ASISTENTES_URL, json=payload, headers=auth_headers(gerente))
    assert r.status_code == 422
    assert r.json()["field"] == "contrasena"
    assert db.scalar(select(Usuario).where(Usuario.nombres == "Lorena")) is None


@pytest.mark.parametrize("username", ["ab", "a" * 31, "dos palabras", "ñandu", "a@b.com"])
def test_username_elegido_fuera_de_la_regla_comun(
    cliente: TestClient, dos_gerentes: DosGerentes, username: str
) -> None:
    """El username elegido sigue ck_usuario_username: uno de 31 caracteres no llega a la base."""
    gerente = dos_gerentes.uno.gerente
    payload = {"nombres": "Lorena", "apellidos": "Quispe", "username": username}
    r = cliente.post(ASISTENTES_URL, json=payload, headers=auth_headers(gerente))
    assert r.status_code == 422
    assert r.json()["field"] == "username"


def test_rechazo_por_permisos_solo_gerente(
    cliente: TestClient,
    dos_gerentes: DosGerentes,
) -> None:
    """Una asistente no tiene permiso para crear otra asistente (403 SIN_PERMISO)."""
    asistente = dos_gerentes.uno.asistente
    payload = {
        "nombres": "Daniela",
        "apellidos": "Vargas",
    }
    r = cliente.post(ASISTENTES_URL, json=payload, headers=auth_headers(asistente))
    assert r.status_code == 403
    assert r.json()["code"] == "SIN_PERMISO"

    # Sin autenticación responde 401
    r_anon = cliente.post(ASISTENTES_URL, json=payload)
    assert r_anon.status_code == 401


def test_regla_una_activa_por_gerente_desactiva_anterior(
    cliente: TestClient,
    dos_gerentes: DosGerentes,
    db: Session,
) -> None:
    """Una activa por gerente: activar ahora reutiliza TASK-14 desactivando la anterior."""
    gerente = dos_gerentes.uno.gerente
    asistente_antigua = dos_gerentes.uno.asistente
    assert asistente_antigua.estado == "activa"

    payload = {
        "nombres": "Beatriz",
        "apellidos": "Nuñez",
        "activar_ahora": True,
    }
    r = cliente.post(ASISTENTES_URL, json=payload, headers=auth_headers(gerente))
    assert r.status_code == 201
    nueva_id = r.json()["id"]

    # Verificar que la antigua pasó a inactiva
    db.refresh(asistente_antigua)
    assert asistente_antigua.estado == "inactiva"

    # Verificar que la nueva está activa
    nueva_asistente = db.get(Usuario, nueva_id)
    assert nueva_asistente is not None
    assert nueva_asistente.estado == "activa"

    # Verificar auditoría de desactivación y activación
    ev_desactivada = db.scalar(
        select(Auditoria).where(
            Auditoria.entidad_id == asistente_antigua.id,
            Auditoria.accion == "cuenta_desactivada",
        )
    )
    assert ev_desactivada is not None

    ev_activada = db.scalar(
        select(Auditoria).where(
            Auditoria.entidad_id == nueva_asistente.id,
            Auditoria.accion == "cuenta_activada",
        )
    )
    assert ev_activada is not None


def test_crear_asistente_inactiva(
    cliente: TestClient,
    dos_gerentes: DosGerentes,
    db: Session,
) -> None:
    """Si activar_ahora es False, la existente sigue activa y la nueva queda inactiva."""
    gerente = dos_gerentes.uno.gerente
    asistente_antigua = dos_gerentes.uno.asistente
    assert asistente_antigua.estado == "activa"

    payload = {
        "nombres": "Inés",
        "apellidos": "Bustamante",
        "activar_ahora": False,
    }
    r = cliente.post(ASISTENTES_URL, json=payload, headers=auth_headers(gerente))
    assert r.status_code == 201
    nueva_id = r.json()["id"]

    db.refresh(asistente_antigua)
    assert asistente_antigua.estado == "activa"

    nueva_asistente = db.get(Usuario, nueva_id)
    assert nueva_asistente is not None
    assert nueva_asistente.estado == "inactiva"


def test_concurrencia_creacion_asistentes() -> None:
    """Peticiones simultáneas serializan con bloqueo sin violar uq_usuario_asistente_activa."""
    marca = uuid.uuid4().hex[:8]
    with SessionLocal() as db_setup:
        gerente = Usuario(rol="gerente", username=f"g_conc_{marca}", password_hash="x")
        db_setup.add(gerente)
        db_setup.commit()
        db_setup.refresh(gerente)
        gerente_id = gerente.id

    nombres_lista = ["Ana Maria", "Beatriz Elena", "Carmen Rosa"]

    try:

        def crear_en_hilo(indice: int) -> int:
            with SessionLocal() as sesion_hilo:
                from app.core.dependencias import Origen
                from app.schemas.asistentes import CrearAsistenteEntrada
                from app.services.asistentes import crear_asistente

                g = sesion_hilo.get(Usuario, gerente_id)
                assert g is not None
                datos = CrearAsistenteEntrada(
                    nombres=nombres_lista[indice],
                    apellidos="Torres Rojas",
                    activar_ahora=True,
                )
                origen = Origen(dispositivo="pytest", ip=None)
                asistente, _ = crear_asistente(sesion_hilo, g, datos, origen)
                return 1 if asistente.estado == "activa" else 0

        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
            futuros = [executor.submit(crear_en_hilo, i) for i in range(3)]
            resultados = [f.result() for f in futuros]

        # Todas las creaciones concurrentes se completaron
        assert sum(resultados) == 3

        # Al final, exactamente 1 asistente está activa para ese gerente
        with SessionLocal() as sesion_final:
            activas = sesion_final.scalars(
                select(Usuario).where(
                    Usuario.gerente_id == gerente_id,
                    Usuario.rol == "asistente",
                    Usuario.estado == "activa",
                    Usuario.eliminado_en.is_(None),
                )
            ).all()
            assert len(activas) == 1
    finally:
        with SessionLocal() as db_cleanup:
            from sqlalchemy import text

            db_cleanup.execute(
                text(
                    "DELETE FROM historial_contrasena WHERE usuario_id IN "
                    "(SELECT id FROM usuario WHERE gerente_id = :gid OR id = :gid)"
                ),
                {"gid": gerente_id},
            )
            db_cleanup.execute(
                text("DELETE FROM activacion_cuenta WHERE realizada_por = :gid"),
                {"gid": gerente_id},
            )
            db_cleanup.execute(
                text("DELETE FROM auditoria WHERE gerente_id = :gid"),
                {"gid": gerente_id},
            )
            db_cleanup.execute(
                text("DELETE FROM usuario WHERE gerente_id = :gid"),
                {"gid": gerente_id},
            )
            db_cleanup.execute(
                text("DELETE FROM usuario WHERE id = :gid"),
                {"gid": gerente_id},
            )
            db_cleanup.commit()
