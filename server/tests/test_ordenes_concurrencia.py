"""Responder órdenes con transacciones reales y simultáneas.

Como en test_inicio_pago_concurrencia.py, cada participante abre su propia sesión y confirma con
commit; cada prueba crea gerentes con usernames únicos y los borra en un finally. La cancelación
de TASK-63 y el traspaso de TASK-14 todavía no existen: se reproducen con el orden de bloqueo
acordado (usuario -> orden_pago), que es lo que estas pruebas verifican.
"""

import threading
import time
import uuid
from collections.abc import Callable, Iterator
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.core.database import SessionLocal, engine
from app.core.dependencias import Origen
from app.core.errores import ErrorApi
from app.core.eventos import Evento, TipoEvento
from app.core.seguridad import hashear_contrasena
from app.core.tiempo import ahora_lima
from app.models import Auditoria, Deuda, OrdenPago, Usuario
from app.services.cuenta import bloquear, cambiar_contrasena
from app.services.ordenes import aceptar_orden, publicar_evento_orden
from tests.conftest import nueva_deuda, nueva_orden
from tests.test_inicio_pago_concurrencia import SEGUNDOS_MAXIMOS, abrir, borrar

ORIGEN = Origen(dispositivo="pruebas", ip=None)
# Tiempo para comprobar que una transacción quedó esperando un bloqueo.
ESPERA_OBSERVADA = 0.3

Publicados = list[tuple[uuid.UUID, Evento]]


@dataclass(frozen=True)
class Confirmada:
    gerente_id: uuid.UUID
    asistente_id: uuid.UUID
    deuda_id: uuid.UUID
    orden_id: uuid.UUID


@pytest.fixture
def confirmada(publicados: Publicados) -> Iterator[Callable[[], Confirmada]]:
    """Gerente, asistente, deuda y orden enviada confirmados en la base; se borran al terminar.
    publicados evita enviar a Redis los eventos que salen tras cada commit."""
    gerentes: list[uuid.UUID] = []

    def crear() -> Confirmada:
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
            db.flush()
            deuda = nueva_deuda(db, gerente)
            orden = nueva_orden(db, deuda, asistente=asistente)
            db.commit()
            return Confirmada(gerente.id, asistente.id, deuda.id, orden.id)

    try:
        yield crear
    finally:
        # El cambio de contraseña de TASK-8 deja historial, que borrar() no conoce.
        with engine.begin() as conexion:
            conexion.execute(
                text(
                    "DELETE FROM historial_contrasena WHERE usuario_id IN "
                    "(SELECT id FROM usuario WHERE id = ANY(:ids) OR gerente_id = ANY(:ids))"
                ),
                {"ids": gerentes},
            )
        borrar(gerentes)


@pytest.fixture
def hilos() -> Iterator[ThreadPoolExecutor]:
    ejecutor = ThreadPoolExecutor(max_workers=2)
    try:
        yield ejecutor
    finally:
        # Un hilo colgado no detiene la suite: el lock_timeout lo termina por su cuenta.
        ejecutor.shutdown(wait=False, cancel_futures=True)


def aceptar_y_confirmar(
    usuario_id: uuid.UUID, orden_id: uuid.UUID, salida: threading.Barrier | None = None
) -> bool | ErrorApi:
    """Lo que hace una solicitud de aceptar: su propia sesión, la aceptación y el commit."""
    with abrir() as db:
        # La sesión se valida al recibir la solicitud, antes de cualquier bloqueo.
        usuario = db.get_one(Usuario, usuario_id)
        if salida is not None:
            salida.wait()
        try:
            repetido = aceptar_orden(db, usuario, orden_id, origen=ORIGEN).repetido
        except ErrorApi as error:
            db.rollback()
            return error
        db.commit()
        return repetido


def cancelar_como_task63(db: Session, orden_id: uuid.UUID) -> str:
    """Cancelación de TASK-63: bloquea la orden, la cancela y publica con el ayudante común.
    Devuelve el estado que encontró."""
    orden = db.scalar(select(OrdenPago).where(OrdenPago.id == orden_id).with_for_update())
    assert orden is not None
    encontrado = orden.estado
    orden.estado = "cancelada"
    orden.cancelada_en = ahora_lima()
    db.flush()
    publicar_evento_orden(db, orden, TipoEvento.ORDEN_CANCELADA)
    return encontrado


def cancelar_y_confirmar(orden_id: uuid.UUID) -> str:
    with abrir() as db:
        encontrado = cancelar_como_task63(db, orden_id)
        db.commit()
        return encontrado


def resultado[T](futuro: Future[T]) -> T:
    return futuro.result(timeout=SEGUNDOS_MAXIMOS)


def queda_esperando(futuro: Future[object]) -> bool:
    time.sleep(ESPERA_OBSERVADA)
    return not futuro.done()


def estado_de(confirmada: Confirmada) -> tuple[str, str, uuid.UUID | None]:
    with SessionLocal() as db:
        orden = db.get_one(OrdenPago, confirmada.orden_id)
        deuda = db.get_one(Deuda, confirmada.deuda_id)
        return orden.estado, deuda.estado, deuda.pago_iniciado_por


def contar(confirmada: Confirmada, accion: str) -> int:
    with SessionLocal() as db:
        return (
            db.scalar(
                select(func.count())
                .select_from(Auditoria)
                .where(Auditoria.gerente_id == confirmada.gerente_id, Auditoria.accion == accion)
            )
            or 0
        )


def test_cancelar_primero_hace_que_aceptar_responda_409(
    confirmada: Callable[[], Confirmada], hilos: ThreadPoolExecutor, publicados: Publicados
) -> None:
    datos = confirmada()
    with abrir() as cancela:
        cancelar_como_task63(cancela, datos.orden_id)
        acepta = hilos.submit(aceptar_y_confirmar, datos.asistente_id, datos.orden_id)
        assert queda_esperando(acepta)
        cancela.commit()

    error = resultado(acepta)

    assert isinstance(error, ErrorApi)
    assert (error.status_code, error.code) == (409, "ORDEN_CANCELADA")
    assert estado_de(datos) == ("cancelada", "pendiente", None)
    assert [e.tipo for _, e in publicados] == [TipoEvento.ORDEN_CANCELADA]
    assert publicados[0][1].datos["intento_vigente"] is False


def test_aceptar_primero_conserva_el_intento_al_cancelar(
    confirmada: Callable[[], Confirmada], hilos: ThreadPoolExecutor, publicados: Publicados
) -> None:
    datos = confirmada()
    with abrir() as acepta:
        asistente = acepta.get_one(Usuario, datos.asistente_id)
        aceptar_orden(acepta, asistente, datos.orden_id, origen=ORIGEN)
        cancela = hilos.submit(cancelar_y_confirmar, datos.orden_id)
        assert queda_esperando(cancela)
        acepta.commit()

    # La cancelación esperó y encontró la orden aceptada: el pago iniciado no se revierte.
    assert resultado(cancela) == "aceptada"
    assert estado_de(datos) == ("cancelada", "en_proceso", datos.asistente_id)
    assert [e.tipo for _, e in publicados] == [
        TipoEvento.ORDEN_ACEPTADA,
        TipoEvento.ORDEN_ACEPTADA,
        TipoEvento.ORDEN_CANCELADA,
    ]
    assert publicados[-1][1].datos["intento_vigente"] is True


def test_dos_aceptaciones_simultaneas_inician_una_sola_vez(
    confirmada: Callable[[], Confirmada], hilos: ThreadPoolExecutor
) -> None:
    datos = confirmada()
    salida = threading.Barrier(2, timeout=SEGUNDOS_MAXIMOS)

    futuros = [
        hilos.submit(aceptar_y_confirmar, datos.asistente_id, datos.orden_id, salida)
        for _ in range(2)
    ]
    respuestas = [resultado(futuro) for futuro in futuros]

    # La segunda espera el bloqueo de la orden y encuentra el mismo intento ya iniciado.
    assert sorted(respuestas, key=str) == [False, True]
    assert estado_de(datos) == ("aceptada", "en_proceso", datos.asistente_id)
    assert contar(datos, "orden_aceptada") == 1
    assert contar(datos, "pago_iniciado") == 1


def test_desactivar_a_la_asistente_mientras_acepta_responde_401(
    confirmada: Callable[[], Confirmada], hilos: ThreadPoolExecutor
) -> None:
    datos = confirmada()
    with abrir() as traspaso:
        # TASK-14: bloquea a la asistente, la desactiva y traspasa la orden a la nueva.
        anterior = traspaso.scalar(
            select(Usuario).where(Usuario.id == datos.asistente_id).with_for_update()
        )
        assert anterior is not None
        acepta = hilos.submit(aceptar_y_confirmar, datos.asistente_id, datos.orden_id)
        assert queda_esperando(acepta)
        anterior.estado = "inactiva"
        traspaso.flush()
        nueva = Usuario(
            rol="asistente",
            gerente_id=datos.gerente_id,
            username=f"n_{uuid.uuid4().hex[:12]}",
            password_hash="x",
        )
        traspaso.add(nueva)
        traspaso.flush()
        traspaso.execute(
            text("UPDATE orden_pago SET asistente_id = :nueva WHERE id = :orden"),
            {"nueva": nueva.id, "orden": datos.orden_id},
        )
        nueva_id = nueva.id
        traspaso.commit()

    error = resultado(acepta)

    assert isinstance(error, ErrorApi)
    assert (error.status_code, error.code) == (401, "CUENTA_INACTIVA")
    assert estado_de(datos) == ("enviada", "pendiente", None)
    # La orden traspasada la acepta la asistente nueva.
    assert resultado(hilos.submit(aceptar_y_confirmar, nueva_id, datos.orden_id)) is False
    assert estado_de(datos) == ("aceptada", "en_proceso", nueva_id)


def test_el_traspaso_espera_a_que_termine_la_aceptacion(
    confirmada: Callable[[], Confirmada], hilos: ThreadPoolExecutor
) -> None:
    datos = confirmada()

    def desactivar() -> None:
        with abrir() as traspaso:
            anterior = traspaso.scalar(
                select(Usuario).where(Usuario.id == datos.asistente_id).with_for_update()
            )
            assert anterior is not None
            anterior.estado = "inactiva"
            traspaso.commit()

    with abrir() as acepta:
        asistente = acepta.get_one(Usuario, datos.asistente_id)
        aceptar_orden(acepta, asistente, datos.orden_id, origen=ORIGEN)
        traspaso = hilos.submit(desactivar)
        assert queda_esperando(traspaso)
        acepta.commit()

    resultado(traspaso)
    # Sin interbloqueo: la aceptación se confirmó y el intento queda para que el gerente lo
    # resuelva con cancelar-inicio.
    assert estado_de(datos) == ("aceptada", "en_proceso", datos.asistente_id)


def test_cambiar_la_contrasena_mientras_acepta_responde_401(
    confirmada: Callable[[], Confirmada], hilos: ThreadPoolExecutor
) -> None:
    """TASK-8 bloquea la cuenta y sube token_version: la aceptación, autenticada con el token
    anterior, espera ese bloqueo y después ve la sesión revocada."""
    datos = confirmada()
    with SessionLocal() as db:
        db.get_one(Usuario, datos.asistente_id).password_hash = hashear_contrasena("Actual-2026")
        db.commit()

    with abrir() as cuenta:
        asistente = cuenta.get_one(Usuario, datos.asistente_id)
        bloquear(cuenta, asistente)
        acepta = hilos.submit(aceptar_y_confirmar, datos.asistente_id, datos.orden_id)
        assert queda_esperando(acepta)
        cambiar_contrasena(cuenta, asistente, "Actual-2026", "Nueva-2026", ORIGEN)

    error = resultado(acepta)

    assert isinstance(error, ErrorApi)
    assert (error.status_code, error.code) == (401, "SESION_REVOCADA")
    assert estado_de(datos) == ("enviada", "pendiente", None)
    # Con la sesión renovada (el usuario vuelto a leer) la orden se acepta.
    assert resultado(hilos.submit(aceptar_y_confirmar, datos.asistente_id, datos.orden_id)) is False
    assert estado_de(datos) == ("aceptada", "en_proceso", datos.asistente_id)
