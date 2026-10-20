"""Inicio de pago con transacciones reales y simultáneas.

Estas pruebas no usan el fixture db, que vive en una sola conexión: cada participante abre su
propia sesión y confirma con commit, como dos solicitudes del server. Por eso cada prueba crea
gerentes con usernames únicos y los borra con todo lo suyo en un finally, aunque falle. Cada
transacción fija un lock_timeout y cada hilo un tiempo máximo: una espera que no termina hace
fallar la prueba en lugar de colgar la suite.
"""

import threading
import time
import uuid
from collections.abc import Callable, Iterator
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from decimal import Decimal

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.core.database import SessionLocal, engine
from app.core.dependencias import Origen
from app.core.errores import ErrorApi
from app.core.eventos import Evento
from app.models import Deuda, Limite, Usuario
from app.services.pagos import InicioPago, ResultadoInicio, iniciar_pago
from app.services.saldo import consumo_mes_pen
from tests.conftest import nueva_deuda

ORIGEN = Origen(dispositivo="pruebas", ip=None)
SEGUNDOS_MAXIMOS = 10
# Ninguna transacción de estas pruebas espera un bloqueo más que esto.
ESPERA_BLOQUEO = "5s"


@dataclass(frozen=True)
class Confirmado:
    gerente_id: uuid.UUID
    asistente_id: uuid.UUID
    deudas: list[uuid.UUID]


# Tablas de la prueba en orden de dependencias. La auditoría se borra con SQL directo: el ORM
# la protege de borrados porque en la aplicación solo admite inserciones.
BORRADOS = """
DELETE FROM notificacion WHERE usuario_id IN
  (SELECT id FROM usuario WHERE id = ANY(:ids) OR gerente_id = ANY(:ids));
DELETE FROM auditoria WHERE gerente_id = ANY(:ids);
DELETE FROM comprobante_deuda WHERE deuda_id IN (SELECT id FROM deuda WHERE gerente_id = ANY(:ids));
DELETE FROM comprobante WHERE gerente_id = ANY(:ids);
DELETE FROM solicitud_aprobacion WHERE deuda_id IN
  (SELECT id FROM deuda WHERE gerente_id = ANY(:ids));
DELETE FROM orden_pago WHERE gerente_id = ANY(:ids);
DELETE FROM deuda WHERE gerente_id = ANY(:ids);
DELETE FROM servicio WHERE gerente_id = ANY(:ids);
DELETE FROM categoria WHERE gerente_id = ANY(:ids);
DELETE FROM limite WHERE gerente_id = ANY(:ids);
DELETE FROM usuario WHERE gerente_id = ANY(:ids);
DELETE FROM usuario WHERE id = ANY(:ids);
"""


def borrar(gerentes: list[uuid.UUID]) -> None:
    """Borra los gerentes de la prueba y todo lo que crearon."""
    with engine.begin() as conexion:
        for sentencia in filter(str.strip, BORRADOS.split(";")):
            conexion.execute(text(sentencia), {"ids": gerentes})
        quedan = conexion.scalar(
            text("SELECT count(*) FROM usuario WHERE id = ANY(:ids) OR gerente_id = ANY(:ids)"),
            {"ids": gerentes},
        )
    assert quedan == 0


@pytest.fixture
def confirmados(
    publicados: list[tuple[uuid.UUID, Evento]],
) -> Iterator[Callable[..., Confirmado]]:
    """Crea gerentes confirmados en la base y los borra al terminar. publicados evita enviar a
    Redis las notificaciones que salen tras cada commit."""
    gerentes: list[uuid.UUID] = []

    def crear(*montos: str, mensual: str | None = None) -> Confirmado:
        marca = uuid.uuid4().hex[:12]
        with SessionLocal() as db:
            gerente = Usuario(rol="gerente", username=f"g_{marca}", password_hash="x")
            db.add(gerente)
            db.flush()
            gerentes.append(gerente.id)
            asistente = Usuario(
                rol="asistente", gerente_id=gerente.id, username=f"a_{marca}", password_hash="x"
            )
            db.add(asistente)
            if mensual is not None:
                db.add(Limite(gerente_id=gerente.id, mensual=Decimal(mensual)))
            deudas = [nueva_deuda(db, gerente, monto=monto).id for monto in montos]
            db.commit()
            return Confirmado(gerente.id, asistente.id, deudas)

    try:
        yield crear
    finally:
        borrar(gerentes)


def abrir() -> Session:
    db = SessionLocal()
    db.execute(text(f"SET LOCAL lock_timeout = '{ESPERA_BLOQUEO}'"))
    return db


def iniciar_y_confirmar(
    usuario_id: uuid.UUID, deuda_id: uuid.UUID, antes: Callable[[], object] | None = None
) -> InicioPago | ErrorApi:
    """Lo que hace una solicitud: su propia sesión, el inicio y el commit."""
    with abrir() as db:
        if antes is not None:
            antes()
        usuario = db.get(Usuario, usuario_id)
        assert usuario is not None
        try:
            inicio = iniciar_pago(db, usuario, deuda_id, origen=ORIGEN)
        except ErrorApi as error:
            db.rollback()
            return error
        db.commit()
        return inicio


def resultado(futuro: Future[InicioPago | ErrorApi]) -> InicioPago | ErrorApi:
    return futuro.result(timeout=SEGUNDOS_MAXIMOS)


@pytest.fixture
def hilos() -> Iterator[ThreadPoolExecutor]:
    ejecutor = ThreadPoolExecutor(max_workers=2)
    try:
        yield ejecutor
    finally:
        # Un hilo colgado no detiene la suite: el lock_timeout lo termina por su cuenta.
        ejecutor.shutdown(wait=False, cancel_futures=True)


def estados(deudas: list[uuid.UUID]) -> list[str]:
    with SessionLocal() as db:
        return list(db.scalars(select(Deuda.estado).where(Deuda.id.in_(deudas))))


def test_dos_pagos_simultaneos_del_mismo_gerente_no_superan_el_limite(
    confirmados: Callable[..., Confirmado], hilos: ThreadPoolExecutor
) -> None:
    equipo = confirmados("100.00", "100.00", mensual="150.00")
    salida = threading.Barrier(2, timeout=SEGUNDOS_MAXIMOS)

    futuros = [
        hilos.submit(iniciar_y_confirmar, equipo.asistente_id, deuda, salida.wait)
        for deuda in equipo.deudas
    ]
    resultados = [resultado(f) for f in futuros]

    assert all(isinstance(r, InicioPago) for r in resultados)
    assert sorted(r.resultado for r in resultados if isinstance(r, InicioPago)) == [
        ResultadoInicio.INICIADO,
        ResultadoInicio.REQUIERE_APROBACION,
    ]
    assert sorted(estados(equipo.deudas)) == ["en_proceso", "esperando_aprobacion"]
    with SessionLocal() as db:
        assert consumo_mes_pen(db, equipo.gerente_id) == Decimal("100.00")


def test_el_segundo_pago_espera_al_primero_y_ve_su_reserva(
    confirmados: Callable[..., Confirmado], hilos: ThreadPoolExecutor
) -> None:
    equipo = confirmados("100.00", "100.00", mensual="150.00")
    primero, segundo = equipo.deudas
    with abrir() as db:
        asistente = db.get(Usuario, equipo.asistente_id)
        assert asistente is not None
        iniciar_pago(db, asistente, primero, origen=ORIGEN)

        futuro = hilos.submit(iniciar_y_confirmar, equipo.asistente_id, segundo)
        time.sleep(0.5)
        # Mientras el primero no confirma, el segundo sigue esperando el bloqueo del límite.
        assert not futuro.done()
        db.commit()

    final = resultado(futuro)
    assert isinstance(final, InicioPago)
    assert final.resultado == ResultadoInicio.REQUIERE_APROBACION


def test_la_misma_deuda_simultanea_queda_para_una_sola_persona(
    confirmados: Callable[..., Confirmado], hilos: ThreadPoolExecutor
) -> None:
    equipo = confirmados("80.00")
    [deuda] = equipo.deudas
    salida = threading.Barrier(2, timeout=SEGUNDOS_MAXIMOS)

    futuros = [
        hilos.submit(iniciar_y_confirmar, usuario, deuda, salida.wait)
        for usuario in (equipo.asistente_id, equipo.gerente_id)
    ]
    resultados = [resultado(f) for f in futuros]

    iniciados = [r for r in resultados if isinstance(r, InicioPago)]
    errores = [r for r in resultados if isinstance(r, ErrorApi)]
    assert [r.resultado for r in iniciados] == [ResultadoInicio.INICIADO]
    assert [(e.status_code, e.code) for e in errores] == [(409, "PAGO_EN_CURSO")]
    assert estados(equipo.deudas) == ["en_proceso"]


def test_el_bloqueo_del_limite_es_real(confirmados: Callable[..., Confirmado]) -> None:
    equipo = confirmados("10.00", "10.00", mensual="500.00")
    primero, segundo = equipo.deudas
    with abrir() as db:
        asistente = db.get(Usuario, equipo.asistente_id)
        assert asistente is not None
        iniciar_pago(db, asistente, primero, origen=ORIGEN)

        with SessionLocal() as otra:
            otra.execute(text("SET LOCAL lock_timeout = '200ms'"))
            misma = otra.get(Usuario, equipo.asistente_id)
            assert misma is not None
            with pytest.raises(OperationalError, match="lock timeout"):
                iniciar_pago(otra, misma, segundo, origen=ORIGEN)
        db.rollback()


def test_el_bloqueo_no_alcanza_a_otro_gerente(confirmados: Callable[..., Confirmado]) -> None:
    uno = confirmados("10.00", mensual="500.00")
    dos = confirmados("10.00", mensual="500.00")
    with abrir() as db:
        asistente = db.get(Usuario, uno.asistente_id)
        assert asistente is not None
        iniciar_pago(db, asistente, uno.deudas[0], origen=ORIGEN)

        with SessionLocal() as otra:
            otra.execute(text("SET LOCAL lock_timeout = '200ms'"))
            ajena = otra.get(Usuario, dos.asistente_id)
            assert ajena is not None
            inicio = iniciar_pago(otra, ajena, dos.deudas[0], origen=ORIGEN)
            assert inicio.resultado == ResultadoInicio.INICIADO
            otra.commit()
        db.commit()
