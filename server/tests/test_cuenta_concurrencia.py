"""Cambios de cuenta con transacciones reales y simultáneas.

Estas pruebas no usan el fixture db, que vive en una sola conexión: cada participante abre su
propia sesión y confirma con commit, como dos solicitudes del server. Por eso cada prueba crea
sus gerentes con usernames únicos y los borra con todo lo suyo en un finally, aunque falle. Cada
transacción fija un lock_timeout y cada hilo un tiempo máximo: una espera que no termina hace
fallar la prueba en lugar de colgar la suite.
"""

import threading
import uuid
from collections.abc import Callable, Iterator
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import UTC, datetime

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.core.database import SessionLocal, engine
from app.core.dependencias import Origen
from app.core.errores import ErrorApi
from app.core.seguridad import hashear_contrasena, verificar_contrasena
from app.models import CambioUsuario, HistorialContrasena, Usuario
from app.services.cuenta import cambiar_contrasena, cambiar_usuario

ORIGEN = Origen(dispositivo="pruebas", ip=None)
SEGUNDOS_MAXIMOS = 15
# Ninguna transacción de estas pruebas espera un bloqueo más que esto.
ESPERA_BLOQUEO = "10s"
CONTRASENA = "Clave-segura-1"
HASH = hashear_contrasena(CONTRASENA)

# La auditoría se borra con SQL directo: el ORM la protege de borrados porque en la aplicación
# solo admite inserciones. cambio_usuario e historial_contrasena caen con el usuario (CASCADE).
BORRADOS = """
DELETE FROM auditoria WHERE gerente_id = ANY(:ids);
DELETE FROM usuario WHERE id = ANY(:ids);
"""


def borrar(ids: list[uuid.UUID]) -> None:
    with engine.begin() as conexion:
        for sentencia in filter(str.strip, BORRADOS.split(";")):
            conexion.execute(text(sentencia), {"ids": ids})
        quedan = conexion.scalar(
            text("SELECT count(*) FROM usuario WHERE id = ANY(:ids)"), {"ids": ids}
        )
    assert quedan == 0


@pytest.fixture
def gerentes() -> Iterator[Callable[..., list[uuid.UUID]]]:
    """Crea gerentes confirmados en la base y los borra al terminar."""
    ids: list[uuid.UUID] = []

    def crear(cantidad: int, cambios_previos: int = 0) -> list[uuid.UUID]:
        marca = uuid.uuid4().hex[:12]
        creados: list[uuid.UUID] = []
        with SessionLocal() as db:
            for i in range(cantidad):
                gerente = Usuario(rol="gerente", username=f"g{i}_{marca}", password_hash=HASH)
                db.add(gerente)
                db.flush()
                ids.append(gerente.id)
                creados.append(gerente.id)
                for _ in range(cambios_previos):
                    db.add(
                        CambioUsuario(
                            usuario_id=gerente.id,
                            anterior="a",
                            nuevo="b",
                            creado_en=datetime.now(UTC),
                        )
                    )
            db.commit()
        return creados

    try:
        yield crear
    finally:
        borrar(ids)


@pytest.fixture
def hilos() -> Iterator[ThreadPoolExecutor]:
    ejecutor = ThreadPoolExecutor(max_workers=2)
    try:
        yield ejecutor
    finally:
        # Un hilo colgado no detiene la suite: el lock_timeout lo termina por su cuenta.
        ejecutor.shutdown(wait=False, cancel_futures=True)


def solicitud[T](
    usuario_id: uuid.UUID, accion: Callable[[Session, Usuario], T], salida: threading.Barrier
) -> T | ErrorApi:
    """Lo que hace una solicitud: su propia sesión, la acción y el commit."""
    with SessionLocal() as db:
        db.execute(text(f"SET LOCAL lock_timeout = '{ESPERA_BLOQUEO}'"))
        usuario = db.get(Usuario, usuario_id)
        assert usuario is not None
        salida.wait()
        try:
            return accion(db, usuario)
        except ErrorApi as error:
            db.rollback()
            return error


def resultado[T](futuro: Future[T | ErrorApi]) -> T | ErrorApi:
    return futuro.result(timeout=SEGUNDOS_MAXIMOS)


def codigos(resultados: list[object]) -> list[str]:
    return sorted(r.code for r in resultados if isinstance(r, ErrorApi))


def test_dos_cambios_de_usuario_simultaneos_no_superan_el_limite_del_mes(
    gerentes: Callable[..., list[uuid.UUID]], hilos: ThreadPoolExecutor
) -> None:
    [gerente] = gerentes(1, cambios_previos=1)
    salida = threading.Barrier(2, timeout=SEGUNDOS_MAXIMOS)
    marca = uuid.uuid4().hex[:12]

    futuros = [
        hilos.submit(
            solicitud,
            gerente,
            lambda db, u, nuevo=f"{letra}_{marca}": cambiar_usuario(db, u, nuevo, ORIGEN),
            salida,
        )
        for letra in ("a", "b")
    ]
    resultados = [resultado(f) for f in futuros]

    assert sorted(r for r in resultados if isinstance(r, int)) == [0]
    assert codigos(resultados) == ["LIMITE_EXCEDIDO"]
    with SessionLocal() as db:
        assert (
            db.scalar(
                select(func.count())
                .select_from(CambioUsuario)
                .where(CambioUsuario.usuario_id == gerente)
            )
            == 2
        )


def test_dos_cuentas_que_toman_el_mismo_usuario_simultaneamente_solo_una_lo_logra(
    gerentes: Callable[..., list[uuid.UUID]], hilos: ThreadPoolExecutor
) -> None:
    uno, dos = gerentes(2)
    salida = threading.Barrier(2, timeout=SEGUNDOS_MAXIMOS)
    disputado = f"Disputado_{uuid.uuid4().hex[:12]}"

    futuros = [
        hilos.submit(
            solicitud, quien, lambda db, u, n=nombre: cambiar_usuario(db, u, n, ORIGEN), salida
        )
        for quien, nombre in ((uno, disputado), (dos, disputado.lower()))
    ]
    resultados = [resultado(f) for f in futuros]

    assert sorted(r for r in resultados if isinstance(r, int)) == [1]
    assert codigos(resultados) == ["DUPLICADO"]
    with SessionLocal() as db:
        con_el_usuario = db.scalars(
            select(Usuario.id).where(func.lower(Usuario.username) == disputado.lower())
        ).all()
        assert len(con_el_usuario) == 1


def test_dos_cambios_de_contrasena_simultaneos_con_la_misma_actual_solo_uno_se_aplica(
    gerentes: Callable[..., list[uuid.UUID]], hilos: ThreadPoolExecutor
) -> None:
    [gerente] = gerentes(1)
    salida = threading.Barrier(2, timeout=SEGUNDOS_MAXIMOS)

    futuros = [
        hilos.submit(
            solicitud,
            gerente,
            lambda db, u, nueva=nueva: cambiar_contrasena(db, u, CONTRASENA, nueva, ORIGEN),
            salida,
        )
        for nueva in ("Nueva-uno-1", "Nueva-dos-2")
    ]
    resultados = [resultado(f) for f in futuros]

    # La segunda ve el hash que dejó la primera: su contraseña actual ya no coincide.
    assert sum(isinstance(r, Usuario) for r in resultados) == 1
    assert codigos(resultados) == ["CONTRASENA_INCORRECTA"]
    with SessionLocal() as db:
        final = db.get(Usuario, gerente)
        assert final is not None
        assert final.token_version == 1
        ganadora = next(
            n
            for n in ("Nueva-uno-1", "Nueva-dos-2")
            if verificar_contrasena(n, final.password_hash)
        )
        assert ganadora
        guardadas = db.scalars(
            select(HistorialContrasena.password_hash).where(
                HistorialContrasena.usuario_id == gerente
            )
        ).all()
        assert len(guardadas) == 1
        assert verificar_contrasena(CONTRASENA, guardadas[0])
