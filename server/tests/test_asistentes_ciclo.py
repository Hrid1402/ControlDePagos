"""Cuenta activa única, traspaso de órdenes y eliminación de asistentes (TASK-16, H03).

Amplía test_asistentes_gestion.py: crear con «activar ahora», historial de varios ciclos y
conservación tras la baja, aislamiento entre gerentes y, con transacciones reales y simultáneas,
activar contra desactivar, activar contra eliminar y activar mientras la asistente acepta una
orden. Las pruebas simultáneas confirman sus datos y los borran en un finally, como
test_ordenes_concurrencia.py.
"""

import uuid
from collections.abc import Callable, Iterator
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.database import SessionLocal, engine, get_db
from app.core.dependencias import Origen
from app.core.errores import ErrorApi
from app.core.eventos import TipoEvento
from app.core.seguridad import hashear_contrasena
from app.main import app
from app.models import OrdenPago, Usuario
from app.services.asistentes import (
    Activacion,
    Desactivacion,
    activar_asistente,
    bloquear_gerente,
    desactivar_asistente,
    eliminar_asistente,
)
from app.services.ordenes import aceptar_orden
from tests.conftest import DosGerentes, nueva_deuda, nueva_orden
from tests.test_asistentes_gestion import (
    Publicados,
    acciones_de,
    auth_headers,
    nueva_asistente,
    tipos_para,
)
from tests.test_inicio_pago_concurrencia import SEGUNDOS_MAXIMOS, abrir, borrar
from tests.test_ordenes_concurrencia import queda_esperando

ASISTENTES_URL = "/api/v1/asistentes"
AUDITORIA_URL = "/api/v1/auditoria"
LOGIN_URL = "/api/v1/auth/login"
PERFIL_URL = "/api/v1/usuarios/perfil"
IP = "203.0.113.16"
ORIGEN = Origen(dispositivo="pruebas", ip=None)


@pytest.fixture
def cliente(db: Session) -> Iterator[TestClient]:
    app.dependency_overrides[get_db] = lambda: db
    yield TestClient(app, client=(IP, 50000))
    app.dependency_overrides.pop(get_db, None)


# --- Crear con «activar ahora» ---


def test_crear_con_activar_ahora_reemplaza_a_la_activa_como_activar(
    cliente: TestClient, dos_gerentes: DosGerentes, db: Session, publicados: Publicados
) -> None:
    """Crear la cuenta ya activa es lo mismo que crearla y activarla: la anterior pierde su
    sesión (CA13), sus órdenes sin atender pasan a la nueva (CA14) y ambas quedan en el
    historial de activaciones (CA17)."""
    gerente = dos_gerentes.uno.gerente
    anterior = dos_gerentes.uno.asistente
    version = anterior.token_version
    vista = nueva_orden(db, nueva_deuda(db, gerente), "vista", asistente=anterior)

    r = cliente.post(
        ASISTENTES_URL,
        json={"nombres": "Beatriz", "apellidos": "Núñez", "activar_ahora": True},
        headers=auth_headers(gerente),
    )

    assert r.status_code == 201, r.text
    nueva = db.get_one(Usuario, uuid.UUID(r.json()["id"]))
    db.refresh(anterior)
    db.refresh(vista)
    assert (nueva.estado, anterior.estado) == ("activa", "inactiva")
    assert anterior.token_version == version + 1
    assert TipoEvento.SESION_CERRADA in tipos_para(publicados, anterior)
    assert (vista.asistente_id, vista.estado, vista.vista_en) == (nueva.id, "enviada", None)
    assert acciones_de(db, anterior) == ["desactivada"]
    assert acciones_de(db, nueva) == ["activada"]


def test_crear_sin_asistente_activa_queda_activa_y_en_el_historial(
    cliente: TestClient, dos_gerentes: DosGerentes, db: Session, publicados: Publicados
) -> None:
    gerente = dos_gerentes.uno.gerente
    dos_gerentes.uno.asistente.estado = "inactiva"
    db.flush()

    r = cliente.post(
        ASISTENTES_URL,
        json={"nombres": "Carmen", "apellidos": "Rojas", "activar_ahora": True},
        headers=auth_headers(gerente),
    )

    assert r.status_code == 201, r.text
    nueva = db.get_one(Usuario, uuid.UUID(r.json()["id"]))
    assert nueva.estado == "activa"
    assert acciones_de(db, nueva) == ["activada"]
    assert acciones_de(db, dos_gerentes.uno.asistente) == []
    assert publicados == []


# --- Historial y baja ---


def test_varios_ciclos_quedan_en_el_historial_y_la_baja_conserva_el_nombre(
    cliente: TestClient, dos_gerentes: DosGerentes, db: Session, publicados: Publicados
) -> None:
    """CA15 y CA17: cada cambio queda en el historial con quien lo hizo; tras la baja la cuenta
    sale de la lista, sus acciones siguen en el historial con su nombre y su usuario no se
    libera."""
    gerente = dos_gerentes.uno.gerente
    gerente.nombres, gerente.apellidos = "Jorge", "Salas"
    rosa = dos_gerentes.uno.asistente
    rosa.nombres, rosa.apellidos = "Rosa", "Quispe"
    rosa.password_hash = hashear_contrasena("ClaveSegura2026!")
    db.flush()
    credenciales = {"username": rosa.username, "contrasena": "ClaveSegura2026!"}
    # Una acción propia de la asistente, auditada con su nombre.
    assert cliente.post(LOGIN_URL, json=credenciales).status_code == 200
    lucia = nueva_asistente(db, gerente, "Lucia")
    cabeceras = auth_headers(gerente)

    for cuenta in (lucia, rosa, lucia):
        r = cliente.post(f"{ASISTENTES_URL}/{cuenta.id}/activar", headers=cabeceras)
        assert r.status_code == 200, r.text

    assert acciones_de(db, rosa) == ["desactivada", "activada", "desactivada"]
    assert acciones_de(db, lucia) == ["activada", "desactivada", "activada"]
    detalle = cliente.get(f"{ASISTENTES_URL}/{lucia.id}", headers=cabeceras).json()
    assert [evento["accion"] for evento in detalle["historial"]] == [
        "activada",
        "desactivada",
        "activada",
    ]
    assert {evento["realizada_por"] for evento in detalle["historial"]} == {"Jorge Salas"}

    r = cliente.delete(f"{ASISTENTES_URL}/{rosa.id}", headers=cabeceras)

    assert r.status_code == 204, r.text
    assert acciones_de(db, rosa) == ["desactivada", "activada", "desactivada", "eliminada"]
    lista = cliente.get(ASISTENTES_URL, headers=cabeceras).json()
    assert [cuenta["id"] for cuenta in lista["items"]] == [str(lucia.id)]
    historial = cliente.get(
        AUDITORIA_URL, params={"accion": "login_exitoso"}, headers=cabeceras
    ).json()
    propias = [fila for fila in historial["items"] if fila["usuario_id"] == str(rosa.id)]
    assert [fila["usuario_nombre"] for fila in propias] == ["Rosa Quispe"]
    disponible = cliente.get(
        f"{ASISTENTES_URL}/disponibilidad", params={"username": rosa.username}, headers=cabeceras
    ).json()
    assert disponible["disponible"] is False
    assert cliente.post(LOGIN_URL, json=credenciales).status_code in (401, 403)


def test_traspaso_y_cancelacion_no_tocan_las_ordenes_de_otro_gerente(
    cliente: TestClient, dos_gerentes: DosGerentes, db: Session, publicados: Publicados
) -> None:
    uno, dos = dos_gerentes.uno, dos_gerentes.dos
    ajena = nueva_orden(db, nueva_deuda(db, dos.gerente), "enviada", asistente=dos.asistente)
    propia = nueva_orden(db, nueva_deuda(db, uno.gerente), "enviada", asistente=uno.asistente)
    nueva = nueva_asistente(db, uno.gerente, "Nueva")
    cabeceras = auth_headers(uno.gerente)

    activar = cliente.post(f"{ASISTENTES_URL}/{nueva.id}/activar", headers=cabeceras)
    desactivar = cliente.post(f"{ASISTENTES_URL}/{nueva.id}/desactivar", headers=cabeceras)

    assert activar.json()["ordenes_traspasadas"] == [str(propia.id)]
    assert desactivar.json()["ordenes_canceladas"] == [str(propia.id)]
    db.refresh(ajena)
    db.refresh(dos.asistente)
    assert (ajena.asistente_id, ajena.estado) == (dos.asistente.id, "enviada")
    assert dos.asistente.estado == "activa"
    assert acciones_de(db, dos.asistente) == []
    assert tipos_para(publicados, dos.asistente) == []


# --- Transacciones simultáneas ---


@dataclass(frozen=True)
class Confirmado:
    gerente_id: uuid.UUID
    activa_id: uuid.UUID
    inactiva_id: uuid.UUID
    orden_id: uuid.UUID


@pytest.fixture
def confirmado(publicados: Publicados) -> Iterator[Callable[[], Confirmado]]:
    """Gerente con una asistente activa, otra inactiva y una orden enviada a la activa, todo
    confirmado en la base; se borra al terminar. publicados evita enviar los eventos a Redis."""
    gerentes: list[uuid.UUID] = []

    def crear() -> Confirmado:
        marca = uuid.uuid4().hex[:12]
        with SessionLocal() as db:
            gerente = Usuario(rol="gerente", username=f"g_{marca}", password_hash="x")
            db.add(gerente)
            db.flush()
            gerentes.append(gerente.id)
            activa, inactiva = (
                Usuario(
                    rol="asistente",
                    gerente_id=gerente.id,
                    username=f"{prefijo}_{marca}",
                    password_hash="x",
                    estado=estado,
                )
                for prefijo, estado in (("a", "activa"), ("i", "inactiva"))
            )
            db.add_all([activa, inactiva])
            db.flush()
            orden = nueva_orden(db, nueva_deuda(db, gerente), asistente=activa)
            db.commit()
            return Confirmado(gerente.id, activa.id, inactiva.id, orden.id)

    try:
        yield crear
    finally:
        # borrar() no conoce el historial de activaciones.
        with engine.begin() as conexion:
            conexion.execute(
                text("DELETE FROM activacion_cuenta WHERE realizada_por = ANY(:ids)"),
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


Operacion = Callable[[Session, Usuario], object]


def en_su_sesion(operacion: Operacion, gerente_id: uuid.UUID) -> object:
    """Lo que hace una solicitud del gerente: su propia sesión, la operación y su commit. Un
    ErrorApi se devuelve para comparar el resultado de cada participante."""
    with abrir() as db:
        gerente = db.get_one(Usuario, gerente_id)
        try:
            return operacion(db, gerente)
        except ErrorApi as error:
            db.rollback()
            return error


def resultado(futuro: Future[object]) -> object:
    return futuro.result(timeout=SEGUNDOS_MAXIMOS)


def en_fila(
    hilos: ThreadPoolExecutor, gerente_id: uuid.UUID, primera: Operacion, segunda: Operacion
) -> tuple[object, object]:
    """Retiene al gerente, deja esperando a primera y luego a segunda y las suelta. PostgreSQL
    atiende a quienes esperan la misma fila en el orden en que llegaron, así cada prueba fija
    quién gana la carrera."""
    with abrir() as retiene:
        bloquear_gerente(retiene, retiene.get_one(Usuario, gerente_id))
        uno = hilos.submit(en_su_sesion, primera, gerente_id)
        assert queda_esperando(uno)
        dos = hilos.submit(en_su_sesion, segunda, gerente_id)
        assert queda_esperando(dos)
        retiene.commit()
    return resultado(uno), resultado(dos)


def activar(asistente_id: uuid.UUID) -> Operacion:
    def operacion(db: Session, gerente: Usuario) -> Activacion:
        return activar_asistente(db, gerente, asistente_id, ORIGEN)

    return operacion


def desactivar(asistente_id: uuid.UUID) -> Operacion:
    def operacion(db: Session, gerente: Usuario) -> Desactivacion:
        return desactivar_asistente(db, gerente, asistente_id, ORIGEN)

    return operacion


def eliminar(asistente_id: uuid.UUID) -> Operacion:
    def operacion(db: Session, gerente: Usuario) -> None:
        eliminar_asistente(db, gerente, asistente_id, ORIGEN)

    return operacion


@pytest.mark.parametrize("primero", ["activar", "desactivar"])
def test_activar_y_desactivar_a_la_vez_no_dejan_ordenes_en_una_cuenta_inactiva(
    confirmado: Callable[[], Confirmado], hilos: ThreadPoolExecutor, primero: str
) -> None:
    """El gerente activa a otra mientras desactiva a la actual: en cualquier orden queda una sola
    activa y la orden urgente nunca se queda con una cuenta inactiva."""
    datos = confirmado()
    operaciones = [activar(datos.inactiva_id), desactivar(datos.activa_id)]
    if primero == "desactivar":
        operaciones.reverse()

    resultados = en_fila(hilos, datos.gerente_id, *operaciones)

    assert not any(isinstance(r, ErrorApi) for r in resultados)
    with SessionLocal() as db:
        anterior = db.get_one(Usuario, datos.activa_id)
        nueva = db.get_one(Usuario, datos.inactiva_id)
        orden = db.get_one(OrdenPago, datos.orden_id)
        assert (anterior.estado, nueva.estado) == ("inactiva", "activa")
        assert acciones_de(db, anterior) == ["desactivada"]
        assert acciones_de(db, nueva) == ["activada"]
        if primero == "activar":
            # La orden pasó a la nueva; la desactivación llega tarde y no cambia nada.
            assert (orden.asistente_id, orden.estado) == (nueva.id, "enviada")
            desactivacion = resultados[1]
            assert isinstance(desactivacion, Desactivacion)
            assert desactivacion.repetido
        else:
            # Sin asistente la orden se canceló y no revive al activar a otra.
            assert (orden.asistente_id, orden.estado) == (anterior.id, "cancelada")
            activacion = resultados[1]
            assert isinstance(activacion, Activacion)
            assert (activacion.desactivada, activacion.ordenes_traspasadas) == (None, [])


@pytest.mark.parametrize("primero", ["activar", "eliminar"])
def test_activar_y_eliminar_la_misma_cuenta_a_la_vez(
    confirmado: Callable[[], Confirmado], hilos: ThreadPoolExecutor, primero: str
) -> None:
    """Una cuenta nunca queda eliminada y activa: la segunda operación ve el resultado de la
    primera y se rechaza sin efectos."""
    datos = confirmado()
    operaciones = [activar(datos.inactiva_id), eliminar(datos.inactiva_id)]
    if primero == "eliminar":
        operaciones.reverse()

    _, error = en_fila(hilos, datos.gerente_id, *operaciones)

    assert isinstance(error, ErrorApi)
    with SessionLocal() as db:
        cuenta = db.get_one(Usuario, datos.inactiva_id)
        anterior = db.get_one(Usuario, datos.activa_id)
        orden = db.get_one(OrdenPago, datos.orden_id)
        if primero == "activar":
            assert (error.status_code, error.code) == (409, "CUENTA_ACTIVA")
            assert (cuenta.estado, cuenta.eliminado_en) == ("activa", None)
            assert anterior.estado == "inactiva"
            assert orden.asistente_id == cuenta.id
            assert acciones_de(db, cuenta) == ["activada"]
        else:
            assert (error.status_code, error.code) == (404, "NO_ENCONTRADO")
            assert cuenta.estado == "inactiva"
            assert cuenta.eliminado_en is not None
            assert anterior.estado == "activa"
            assert orden.asistente_id == anterior.id
            assert acciones_de(db, cuenta) == ["eliminada"]
            assert acciones_de(db, anterior) == []


def test_activar_a_otra_espera_la_aceptacion_y_no_traspasa_la_orden_aceptada(
    confirmado: Callable[[], Confirmado], hilos: ThreadPoolExecutor
) -> None:
    """Con los servicios reales de TASK-14 y TASK-68: la activación espera a que la asistente
    termine de aceptar y la orden aceptada, con su intento de pago, se queda con ella."""
    datos = confirmado()
    with abrir() as acepta:
        asistente = acepta.get_one(Usuario, datos.activa_id)
        aceptar_orden(acepta, asistente, datos.orden_id, origen=ORIGEN)
        activa_otra = hilos.submit(en_su_sesion, activar(datos.inactiva_id), datos.gerente_id)
        assert queda_esperando(activa_otra)
        acepta.commit()

    activacion = resultado(activa_otra)

    assert isinstance(activacion, Activacion)
    assert activacion.ordenes_traspasadas == []
    with SessionLocal() as db:
        orden = db.get_one(OrdenPago, datos.orden_id)
        assert (orden.asistente_id, orden.estado) == (datos.activa_id, "aceptada")
        assert db.get_one(Usuario, datos.inactiva_id).estado == "activa"


def test_la_asistente_reemplazada_ya_no_acepta_y_la_nueva_si(
    confirmado: Callable[[], Confirmado], hilos: ThreadPoolExecutor
) -> None:
    """La anterior pidió aceptar con su sesión ya validada, pero la activación de otra se
    confirmó antes: recibe 401 y la orden traspasada la acepta la nueva."""
    datos = confirmado()
    with abrir() as acepta:
        anterior = acepta.get_one(Usuario, datos.activa_id)
        activacion = resultado(
            hilos.submit(en_su_sesion, activar(datos.inactiva_id), datos.gerente_id)
        )
        assert isinstance(activacion, Activacion)
        assert [orden.id for orden in activacion.ordenes_traspasadas] == [datos.orden_id]

        with pytest.raises(ErrorApi) as error:
            aceptar_orden(acepta, anterior, datos.orden_id, origen=ORIGEN)
        assert (error.value.status_code, error.value.code) == (401, "CUENTA_INACTIVA")

    with abrir() as acepta:
        nueva = acepta.get_one(Usuario, datos.inactiva_id)
        aceptar_orden(acepta, nueva, datos.orden_id, origen=ORIGEN)
        acepta.commit()
    with SessionLocal() as db:
        orden = db.get_one(OrdenPago, datos.orden_id)
        assert (orden.asistente_id, orden.estado) == (datos.inactiva_id, "aceptada")
