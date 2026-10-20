"""Intentos de ingreso simultáneos con transacciones reales (H01 CA06).

Estas pruebas no usan el fixture db, que vive en una sola conexión: cada intento abre su propia
sesión y confirma con commit, como solicitudes paralelas al server. Cada prueba crea sus cuentas
con usernames únicos y las borra con su auditoría en un finally, aunque falle. Cada transacción
fija un lock_timeout y cada hilo un tiempo máximo: una espera que no termina hace fallar la prueba
en lugar de colgar la suite.

iniciar_sesion bloquea la fila del usuario con FOR UPDATE hasta el commit, así que los intentos
simultáneos se atienden de uno en uno y cada uno ve el contador que dejó el anterior. Los
resultados esperados se derivan de esa serialización: si alguno falla, revisar el bloqueo de
la fila antes de aflojar la prueba.
"""

import threading
import uuid
from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import select, text

from app.core.database import SessionLocal, engine
from app.core.dependencias import Origen
from app.core.errores import ErrorApi
from app.core.seguridad import hashear_contrasena
from app.models import Auditoria, Usuario
from app.services.acceso import iniciar_sesion

ORIGEN = Origen(dispositivo="pruebas", ip=None)
SEGUNDOS_MAXIMOS = 15
# Ninguna transacción de estas pruebas espera un bloqueo más que esto.
ESPERA_BLOQUEO = "10s"
CONTRASENA = "Clave-segura-1"
INCORRECTA = "Clave-incorrecta-1"
HASH = hashear_contrasena(CONTRASENA)

# La auditoría se borra con SQL directo: el ORM la protege de borrados porque en la aplicación
# solo admite inserciones. La de la asistente también lleva el gerente_id de su gerente.
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
def cuentas() -> Iterator[Callable[..., Usuario]]:
    """Crea una cuenta confirmada en la base, con su gerente si es asistente, y la borra al
    terminar. Devuelve una copia desconectada para leer su id y su username."""
    ids: list[uuid.UUID] = []

    def crear(
        rol: str = "gerente", intentos: int = 0, bloqueado_hasta: datetime | None = None
    ) -> Usuario:
        marca = uuid.uuid4().hex[:12]
        with SessionLocal(expire_on_commit=False) as db:
            gerente = Usuario(rol="gerente", username=f"g_{marca}", password_hash=HASH)
            db.add(gerente)
            db.flush()
            ids.append(gerente.id)
            cuenta = gerente
            if rol == "asistente":
                cuenta = Usuario(
                    rol="asistente",
                    gerente_id=gerente.id,
                    username=f"a_{marca}",
                    password_hash=HASH,
                )
                db.add(cuenta)
                db.flush()
                ids.insert(0, cuenta.id)
            cuenta.intentos_fallidos = intentos
            cuenta.bloqueado_hasta = bloqueado_hasta
            db.commit()
            return cuenta

    try:
        yield crear
    finally:
        borrar(ids)


def intento(username: str, contrasena: str, salida: threading.Barrier) -> str:
    """Lo que hace una solicitud de login: su propia sesión, el intento y el commit. Devuelve
    "ingreso" o el código del error."""
    with SessionLocal() as db:
        db.execute(text(f"SET LOCAL lock_timeout = '{ESPERA_BLOQUEO}'"))
        salida.wait()
        try:
            iniciar_sesion(db, username, contrasena, ORIGEN)
        except ErrorApi as error:
            return error.code
        return "ingreso"


def simultaneos(username: str, contrasenas: list[str]) -> list[str]:
    """Lanza un intento por contraseña, todos a la vez, y devuelve sus resultados en orden."""
    salida = threading.Barrier(len(contrasenas), timeout=SEGUNDOS_MAXIMOS)
    ejecutor = ThreadPoolExecutor(max_workers=len(contrasenas))
    try:
        futuros = [ejecutor.submit(intento, username, c, salida) for c in contrasenas]
        return [futuro.result(timeout=SEGUNDOS_MAXIMOS) for futuro in futuros]
    finally:
        # Un hilo colgado no detiene la suite: el lock_timeout lo termina por su cuenta.
        ejecutor.shutdown(wait=False, cancel_futures=True)


def estado(usuario_id: uuid.UUID) -> Usuario:
    with SessionLocal(expire_on_commit=False) as db:
        return db.get_one(Usuario, usuario_id)


def fallidos(usuario_id: uuid.UUID) -> list[dict[str, Any]]:
    """Detalle de cada login_fallido de la cuenta, en orden de registro."""
    with SessionLocal() as db:
        return list(
            db.scalars(
                select(Auditoria.detalle)
                .where(Auditoria.usuario_id == usuario_id, Auditoria.accion == "login_fallido")
                .order_by(Auditoria.creado_en, Auditoria.id)
            )
        )


@pytest.mark.parametrize("rol", ["gerente", "asistente"])
def test_ocho_fallos_simultaneos_bloquean_en_el_quinto_sin_pasar_de_cinco(
    cuentas: Callable[..., Usuario], rol: str
) -> None:
    cuenta = cuentas(rol)

    resultados = simultaneos(cuenta.username, [INCORRECTA] * 8)

    # Atendidos de uno en uno: los cuatro primeros suben el contador de 1 a 4 y responden el 401
    # genérico. El quinto llega a 5, bloquea y ya responde 423. Los tres últimos encuentran la
    # cuenta bloqueada: responden 423 sin verificar la contraseña ni sumar intentos.
    assert sorted(resultados) == ["CREDENCIALES_INVALIDAS"] * 4 + ["CUENTA_BLOQUEADA"] * 4
    final = estado(cuenta.id)
    assert final.intentos_fallidos == 5
    assert final.bloqueado_hasta is not None
    restante = final.bloqueado_hasta - datetime.now(UTC)
    assert timedelta(minutes=14) < restante <= timedelta(minutes=15)

    # Cada intento queda auditado. El quinto sigue siendo una contraseña incorrecta (es el que
    # bloquea); solo los posteriores se registran como cuenta_bloqueada. Que el contador
    # auditado vaya de 1 a 5 sin repetir prueba que ningún intento leyó un contador viejo.
    eventos = fallidos(cuenta.id)
    incorrectas = [e for e in eventos if e["motivo"] == "contrasena_incorrecta"]
    assert sorted(e["intentos_fallidos"] for e in incorrectas) == [1, 2, 3, 4, 5]
    assert [e["motivo"] for e in eventos].count("cuenta_bloqueada") == 3
    assert len(eventos) == 8


def test_con_cuatro_fallos_previos_solo_un_intento_simultaneo_bloquea(
    cuentas: Callable[..., Usuario],
) -> None:
    cuenta = cuentas(intentos=4)

    resultados = simultaneos(cuenta.username, [INCORRECTA] * 3)

    # Los tres responden 423: el primero porque su fallo es el quinto y bloquea, los otros dos
    # porque ya la encuentran bloqueada. El bloqueo se fija una sola vez: los intentos
    # posteriores no lo alargan ni suben el contador por encima de 5.
    assert resultados == ["CUENTA_BLOQUEADA"] * 3
    final = estado(cuenta.id)
    assert final.intentos_fallidos == 5
    eventos = fallidos(cuenta.id)
    [bloqueo] = [e for e in eventos if e["motivo"] == "contrasena_incorrecta"]
    assert bloqueo["intentos_fallidos"] == 5
    assert final.bloqueado_hasta is not None
    assert datetime.fromisoformat(bloqueo["bloqueado_hasta"]) == final.bloqueado_hasta
    assert [e["motivo"] for e in eventos].count("cuenta_bloqueada") == 2


def test_con_cuatro_fallos_un_ingreso_y_un_fallo_simultaneos_quedan_en_un_orden_valido(
    cuentas: Callable[..., Usuario],
) -> None:
    cuenta = cuentas(intentos=4)

    correcto, incorrecto = simultaneos(cuenta.username, [CONTRASENA, INCORRECTA])

    final = estado(cuenta.id)
    # Solo hay dos órdenes posibles y el estado final debe corresponder a uno de ellos:
    # - Entra primero el correcto: ingresa y reinicia el contador; el fallo posterior lo deja
    #   en 1 con el 401 genérico, sin bloqueo.
    # - Entra primero el fallo: es el quinto y bloquea; el correcto encuentra la cuenta
    #   bloqueada y responde 423 aunque la contraseña sea buena.
    # Cualquier mezcla (ingresar con 5 fallos, 401 con el contador en 5, etc.) es un error.
    if correcto == "ingreso":
        assert incorrecto == "CREDENCIALES_INVALIDAS"
        assert (final.intentos_fallidos, final.bloqueado_hasta) == (1, None)
        assert final.ultimo_ingreso is not None
    else:
        assert (correcto, incorrecto) == ("CUENTA_BLOQUEADA", "CUENTA_BLOQUEADA")
        assert final.intentos_fallidos == 5
        assert final.bloqueado_hasta is not None
        assert final.ultimo_ingreso is None


def test_al_vencer_el_bloqueo_dos_fallos_simultaneos_cuentan_los_dos(
    cuentas: Callable[..., Usuario],
) -> None:
    cuenta = cuentas(intentos=5, bloqueado_hasta=datetime.now(UTC) - timedelta(seconds=1))

    resultados = simultaneos(cuenta.username, [INCORRECTA] * 2)

    # El primero ve el bloqueo vencido, reinicia el contador a 0 y suma su fallo: 1. El segundo
    # ya no ve bloqueo y suma el suyo: 2. Si el reinicio se aplicara dos veces, o el segundo
    # leyera el contador viejo, el final sería 1.
    assert resultados == ["CREDENCIALES_INVALIDAS"] * 2
    final = estado(cuenta.id)
    assert (final.intentos_fallidos, final.bloqueado_hasta) == (2, None)
