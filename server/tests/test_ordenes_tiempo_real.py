"""Eventos orden_* (H19): publicar_evento_orden, entrega por WebSocket y recuperación por la API.

Las pruebas del canal usan el WebSocket real con Redis, como test_tiempo_real.py: el evento sale
solo tras el commit y cada conexión revalida su sesión antes de recibirlo.
"""

import threading
import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencias import Origen, obtener_fabrica_sesiones
from app.core.eventos import Evento, TipoEvento
from app.core.seguridad import crear_token
from app.main import app
from app.models import Deuda, OrdenPago, Usuario
from app.services.ordenes import aceptar_orden, publicar_evento_orden
from app.services.pagos import iniciar_pago
from tests.conftest import DosGerentes, Equipo, nueva_deuda, nueva_orden
from tests.test_tiempo_real import RUTA, autenticar, esperar_cierre, siguiente_es_marcador

Publicados = list[tuple[uuid.UUID, Evento]]
PENDIENTES = "/api/v1/ordenes/pendientes"
ORIGEN = Origen(dispositivo="pruebas", ip=None)


def orden_de(db: Session, equipo: Equipo, estado: str = "enviada") -> OrdenPago:
    deuda = nueva_deuda(db, equipo.gerente)
    return nueva_orden(db, deuda, estado=estado, asistente=equipo.asistente)


def cancelar(db: Session, orden: OrdenPago) -> None:
    """Lo que hará TASK-63 al cancelar: cambia la orden y publica con el ayudante común."""
    orden.estado = "cancelada"
    db.flush()
    publicar_evento_orden(db, orden, TipoEvento.ORDEN_CANCELADA)


# publicar_evento_orden


@pytest.mark.parametrize(
    ("tipo", "estado", "a_gerente"),
    [
        (TipoEvento.ORDEN_NUEVA, "enviada", False),
        (TipoEvento.ORDEN_CANCELADA, "cancelada", False),
        (TipoEvento.ORDEN_VISTA, "vista", True),
        (TipoEvento.ORDEN_ACEPTADA, "aceptada", True),
        (TipoEvento.ORDEN_RECHAZADA, "rechazada", True),
    ],
)
def test_cada_evento_va_a_sus_destinatarios_tras_el_commit(
    db: Session,
    dos_gerentes: DosGerentes,
    publicados: Publicados,
    tipo: TipoEvento,
    estado: str,
    a_gerente: bool,
) -> None:
    equipo = dos_gerentes.uno
    orden = orden_de(db, equipo, estado)

    publicar_evento_orden(db, orden, tipo)

    assert publicados == []
    db.commit()
    esperados = [equipo.gerente.id, equipo.asistente.id] if a_gerente else [equipo.asistente.id]
    assert [destinatario for destinatario, _ in publicados] == esperados
    # Un solo evento: sus copias comparten el id con el que el cliente descarta repetidos.
    assert len({evento.id for _, evento in publicados}) == 1
    evento = publicados[0][1]
    assert evento.tipo == tipo
    assert {k: evento.datos[k] for k in ("orden_id", "deuda_id", "estado", "version")} == {
        "orden_id": str(orden.id),
        "deuda_id": str(orden.deuda_id),
        "estado": estado,
        "version": f"{estado}:0",
    }


def test_orden_nueva_lleva_la_orden_completa(
    db: Session, dos_gerentes: DosGerentes, publicados: Publicados
) -> None:
    orden = orden_de(db, dos_gerentes.uno)

    publicar_evento_orden(db, orden, TipoEvento.ORDEN_NUEVA)
    db.commit()

    [(_, evento)] = publicados
    completa = evento.datos["orden"]
    assert (completa["id"], completa["monto"], completa["moneda"], completa["empresa"]) == (
        str(orden.id),
        "100.00",
        "PEN",
        "Hidrandina",
    )


@pytest.mark.parametrize(("aceptada", "vigente"), [(False, False), (True, True)])
def test_orden_cancelada_indica_si_sigue_el_intento(
    db: Session,
    dos_gerentes: DosGerentes,
    publicados: Publicados,
    aceptada: bool,
    vigente: bool,
) -> None:
    equipo = dos_gerentes.uno
    orden = orden_de(db, equipo, "aceptada" if aceptada else "enviada")
    if aceptada:
        iniciar_pago(db, equipo.asistente, orden.deuda_id, origen=ORIGEN)

    cancelar(db, orden)
    db.commit()

    [(_, evento)] = publicados
    assert evento.datos["intento_vigente"] is vigente
    assert db.get_one(Deuda, orden.deuda_id).estado == ("en_proceso" if aceptada else "pendiente")


def test_orden_sin_asistente_solo_avisa_al_gerente(
    db: Session, dos_gerentes: DosGerentes, publicados: Publicados
) -> None:
    equipo = dos_gerentes.uno
    orden = nueva_orden(db, nueva_deuda(db, equipo.gerente), estado="vista")

    publicar_evento_orden(db, orden, TipoEvento.ORDEN_NUEVA)
    publicar_evento_orden(db, orden, TipoEvento.ORDEN_VISTA)
    db.commit()

    assert [(d, e.tipo) for d, e in publicados] == [(equipo.gerente.id, TipoEvento.ORDEN_VISTA)]


def test_otro_tipo_de_evento_no_es_de_orden(db: Session, dos_gerentes: DosGerentes) -> None:
    orden = orden_de(db, dos_gerentes.uno)

    with pytest.raises(ValueError):
        publicar_evento_orden(db, orden, TipoEvento.NOTIFICACION)


def test_rollback_descarta_el_evento(
    db: Session, dos_gerentes: DosGerentes, publicados: Publicados
) -> None:
    orden = orden_de(db, dos_gerentes.uno)
    with pytest.raises(RuntimeError), db.begin_nested():
        publicar_evento_orden(db, orden, TipoEvento.ORDEN_NUEVA)
        raise RuntimeError("falla antes del commit")

    db.commit()

    assert publicados == []


def test_evento_repetido_conserva_la_version_y_el_reenvio_la_cambia(
    db: Session, dos_gerentes: DosGerentes, publicados: Publicados
) -> None:
    orden = orden_de(db, dos_gerentes.uno)
    publicar_evento_orden(db, orden, TipoEvento.ORDEN_NUEVA)
    # Un job que se repite sin cambiar la orden publica otra vez el mismo contenido.
    publicar_evento_orden(db, orden, TipoEvento.ORDEN_NUEVA)
    orden.reenvios = 1
    db.flush()
    publicar_evento_orden(db, orden, TipoEvento.ORDEN_NUEVA)
    db.commit()

    versiones = [(e.datos["orden_id"], e.datos["version"]) for _, e in publicados]
    assert versiones == [(str(orden.id), "enviada:0")] * 2 + [(str(orden.id), "enviada:1")]


# Canal WebSocket


@pytest.fixture
def candado() -> threading.Lock:
    return threading.Lock()


@pytest.fixture
def cliente(db: Session, candado: threading.Lock) -> Iterator[TestClient]:
    # El WebSocket valida en otro hilo con la misma sesión de la prueba: el candado evita usarla
    # mientras la prueba hace commit. La API también usa esa sesión, que ve los datos de la prueba.
    @contextmanager
    def sesion_compartida() -> Iterator[Session]:
        with candado:
            yield db

    app.dependency_overrides[obtener_fabrica_sesiones] = lambda: sesion_compartida
    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app) as cliente:
        yield cliente
    app.dependency_overrides.clear()


@pytest.fixture
def confirmar(db: Session, candado: threading.Lock) -> Callable[[], None]:
    def commit() -> None:
        with candado:
            db.commit()

    return commit


def cabecera(usuario: Usuario) -> dict[str, str]:
    return {"Authorization": f"Bearer {crear_token(usuario)}"}


def test_la_orden_llega_sin_recargar_solo_a_su_asistente(
    cliente: TestClient,
    db: Session,
    dos_gerentes: DosGerentes,
    confirmar: Callable[[], None],
) -> None:
    uno, dos = dos_gerentes.uno, dos_gerentes.dos
    with (
        cliente.websocket_connect(RUTA) as asistente_uno,
        cliente.websocket_connect(RUTA) as asistente_dos,
        cliente.websocket_connect(RUTA) as gerente_uno,
    ):
        autenticar(asistente_uno, crear_token(uno.asistente))
        autenticar(asistente_dos, crear_token(dos.asistente))
        autenticar(gerente_uno, crear_token(uno.gerente))
        orden = orden_de(db, uno)
        publicar_evento_orden(db, orden, TipoEvento.ORDEN_NUEVA)
        confirmar()

        evento = asistente_uno.receive_json()
        assert (evento["tipo"], evento["datos"]["orden_id"]) == ("orden_nueva", str(orden.id))
        siguiente_es_marcador(asistente_dos, dos.asistente)
        siguiente_es_marcador(gerente_uno, uno.gerente)


def test_aceptar_avisa_al_gerente_y_a_las_otras_pestanas(
    cliente: TestClient,
    db: Session,
    dos_gerentes: DosGerentes,
    confirmar: Callable[[], None],
) -> None:
    equipo = dos_gerentes.uno
    orden = orden_de(db, equipo)
    with (
        cliente.websocket_connect(RUTA) as gerente,
        cliente.websocket_connect(RUTA) as otra_pestana,
    ):
        autenticar(gerente, crear_token(equipo.gerente))
        autenticar(otra_pestana, crear_token(equipo.asistente))

        # La solicitud de una pestaña; el commit lo hace la prueba con el candado tomado.
        aceptar_orden(db, equipo.asistente, orden.id, origen=ORIGEN)
        confirmar()

        for ws in (gerente, otra_pestana):
            evento = ws.receive_json()
            assert (evento["tipo"], evento["datos"]["version"]) == ("orden_aceptada", "aceptada:0")


def test_al_reconectar_la_api_recupera_lo_que_llego_o_se_cancelo_sin_conexion(
    cliente: TestClient,
    db: Session,
    dos_gerentes: DosGerentes,
    confirmar: Callable[[], None],
) -> None:
    equipo = dos_gerentes.uno
    with cliente.websocket_connect(RUTA) as ws:
        autenticar(ws, crear_token(equipo.asistente))
    # Sin conexión: los eventos no llegan a nadie, pero las órdenes quedan en la base.
    queda = orden_de(db, equipo)
    cancelada = orden_de(db, equipo)
    publicar_evento_orden(db, queda, TipoEvento.ORDEN_NUEVA)
    publicar_evento_orden(db, cancelada, TipoEvento.ORDEN_NUEVA)
    confirmar()
    cancelar(db, cancelada)
    confirmar()

    with cliente.websocket_connect(RUTA) as ws:
        autenticar(ws, crear_token(equipo.asistente))
        # Lo publicado sin conexión no se reenvía: el cliente lo pide por la API al conectarse.
        siguiente_es_marcador(ws, equipo.asistente)
        r = cliente.get(PENDIENTES, headers=cabecera(equipo.asistente))

    assert [item["id"] for item in r.json()["items"]] == [str(queda.id)]


def test_la_cancelacion_cierra_la_orden_en_pantalla(
    cliente: TestClient,
    db: Session,
    dos_gerentes: DosGerentes,
    confirmar: Callable[[], None],
) -> None:
    equipo = dos_gerentes.uno
    orden = orden_de(db, equipo)
    with cliente.websocket_connect(RUTA) as ws:
        autenticar(ws, crear_token(equipo.asistente))
        cancelar(db, orden)
        confirmar()
        evento = ws.receive_json()

    assert evento["tipo"] == "orden_cancelada"
    assert evento["datos"]["intento_vigente"] is False
    r = cliente.post(f"/api/v1/ordenes/{orden.id}/aceptar", headers=cabecera(equipo.asistente))
    assert r.json()["code"] == "ORDEN_CANCELADA"


def test_token_revocado_no_recibe_la_orden(
    cliente: TestClient,
    db: Session,
    dos_gerentes: DosGerentes,
    confirmar: Callable[[], None],
) -> None:
    equipo = dos_gerentes.uno
    token = crear_token(equipo.asistente)
    with cliente.websocket_connect(RUTA) as ws:
        autenticar(ws, token)
        # Se revoca sin aviso de cierre, como si se hubiera perdido: la entrega lo detecta.
        equipo.asistente.token_version += 1
        orden = orden_de(db, equipo)
        publicar_evento_orden(db, orden, TipoEvento.ORDEN_NUEVA)
        confirmar()
        evento = ws.receive_json()
        cierre = esperar_cierre(ws)

    assert (evento["tipo"], evento["datos"]) == ("sesion_cerrada", {"code": "SESION_REVOCADA"})
    assert cierre.reason == "SESION_REVOCADA"
    r = cliente.get(PENDIENTES, headers={"Authorization": f"Bearer {token}"})
    assert (r.status_code, r.json()["code"]) == (401, "SESION_REVOCADA")
