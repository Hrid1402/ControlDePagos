"""Activar, desactivar, eliminar y restablecer la contraseña de una asistente (TASK-14, H03)."""

import concurrent.futures
import uuid
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.core.database import SessionLocal, get_db
from app.core.dependencias import Origen
from app.core.eventos import Evento, TipoEvento
from app.core.seguridad import crear_token, hashear_contrasena, verificar_contrasena
from app.main import app
from app.models import ActivacionCuenta, Auditoria, HistorialContrasena, Notificacion, Usuario
from app.services.asistentes import activar_asistente
from tests.conftest import DosGerentes, nueva_deuda, nueva_orden

ASISTENTES_URL = "/api/v1/asistentes"
LOGIN_URL = "/api/v1/auth/login"
PERFIL_URL = "/api/v1/usuarios/perfil"
IP = "203.0.113.14"

Publicados = list[tuple[uuid.UUID, Evento]]


def auth_headers(usuario: Usuario) -> dict[str, str]:
    return {"Authorization": f"Bearer {crear_token(usuario)}"}


@pytest.fixture
def cliente(db: Session) -> Iterator[TestClient]:
    app.dependency_overrides[get_db] = lambda: db
    yield TestClient(app, client=(IP, 50000))
    app.dependency_overrides.pop(get_db, None)


def nueva_asistente(
    db: Session, gerente: Usuario, nombre: str, estado: str = "inactiva"
) -> Usuario:
    asistente = Usuario(
        rol="asistente",
        gerente_id=gerente.id,
        username=f"{nombre.lower()}_{uuid.uuid4().hex[:6]}",
        password_hash="x",
        nombres=nombre,
        apellidos="Prueba",
        estado=estado,
    )
    db.add(asistente)
    db.flush()
    return asistente


def acciones_de(db: Session, cuenta: Usuario) -> list[str]:
    return list(
        db.scalars(
            select(ActivacionCuenta.accion)
            .where(ActivacionCuenta.cuenta_id == cuenta.id)
            .order_by(ActivacionCuenta.creado_en, ActivacionCuenta.id)
        )
    )


def tipos_para(publicados: Publicados, usuario: Usuario) -> list[str]:
    return [evento.tipo for destino, evento in publicados if destino == usuario.id]


def test_ca10_activar_desactiva_la_actual_y_cierra_su_sesion(
    cliente: TestClient, dos_gerentes: DosGerentes, db: Session, publicados: Publicados
) -> None:
    gerente = dos_gerentes.uno.gerente
    actual = dos_gerentes.uno.asistente
    token_actual = crear_token(actual)
    nueva = nueva_asistente(db, gerente, "Nueva")

    r = cliente.post(f"{ASISTENTES_URL}/{nueva.id}/activar", headers=auth_headers(gerente))

    assert r.status_code == 200, r.text
    datos = r.json()
    assert datos["activada"]["id"] == str(nueva.id)
    assert datos["activada"]["estado"] == "activa"
    assert datos["desactivada"]["id"] == str(actual.id)
    assert datos["desactivada"]["nombres"] == actual.nombres
    assert datos["desactivada"]["estado"] == "inactiva"
    assert datos["ordenes_traspasadas"] == []

    db.refresh(actual)
    db.refresh(nueva)
    assert (actual.estado, nueva.estado) == ("inactiva", "activa")
    assert acciones_de(db, actual) == ["desactivada"]
    assert acciones_de(db, nueva) == ["activada"]
    assert TipoEvento.SESION_CERRADA in tipos_para(publicados, actual)

    revocada = cliente.get(PERFIL_URL, headers={"Authorization": f"Bearer {token_actual}"})
    assert revocada.status_code == 401
    assert cliente.get(PERFIL_URL, headers=auth_headers(nueva)).status_code == 200


def test_ca10_activar_la_que_ya_esta_activa_no_cambia_nada(
    cliente: TestClient, dos_gerentes: DosGerentes, db: Session
) -> None:
    gerente = dos_gerentes.uno.gerente
    actual = dos_gerentes.uno.asistente
    version = actual.token_version

    r = cliente.post(f"{ASISTENTES_URL}/{actual.id}/activar", headers=auth_headers(gerente))

    assert r.status_code == 200, r.text
    assert r.json()["desactivada"] is None
    db.refresh(actual)
    assert actual.estado == "activa"
    assert actual.token_version == version
    assert acciones_de(db, actual) == []


def test_ca14_activar_traspasa_las_ordenes_sin_atender(
    cliente: TestClient, dos_gerentes: DosGerentes, db: Session, publicados: Publicados
) -> None:
    gerente = dos_gerentes.uno.gerente
    actual = dos_gerentes.uno.asistente
    nueva = nueva_asistente(db, gerente, "Nueva")
    enviada = nueva_orden(db, nueva_deuda(db, gerente), "enviada", asistente=actual)
    vista = nueva_orden(db, nueva_deuda(db, gerente), "vista", asistente=actual)
    aceptada = nueva_orden(db, nueva_deuda(db, gerente), "aceptada", asistente=actual)

    r = cliente.post(f"{ASISTENTES_URL}/{nueva.id}/activar", headers=auth_headers(gerente))

    assert r.status_code == 200, r.text
    assert set(r.json()["ordenes_traspasadas"]) == {str(enviada.id), str(vista.id)}
    for orden in (enviada, vista, aceptada):
        db.refresh(orden)
    assert (enviada.asistente_id, enviada.estado) == (nueva.id, "enviada")
    assert (vista.asistente_id, vista.estado, vista.vista_en) == (nueva.id, "enviada", None)
    # La aceptada ya tiene un intento de pago a nombre de la anterior: no se traspasa.
    assert (aceptada.asistente_id, aceptada.estado) == (actual.id, "aceptada")
    assert tipos_para(publicados, nueva).count(TipoEvento.ORDEN_NUEVA) == 2

    traspasos = db.scalars(select(Auditoria).where(Auditoria.accion == "orden_traspasada")).all()
    assert {registro.entidad_id for registro in traspasos} == {enviada.id, vista.id}


def test_ca11_ca13_desactivar_bloquea_el_acceso_y_cierra_la_sesion(
    cliente: TestClient, dos_gerentes: DosGerentes, db: Session, publicados: Publicados
) -> None:
    gerente = dos_gerentes.uno.gerente
    asistente = dos_gerentes.uno.asistente
    asistente.password_hash = hashear_contrasena("ClaveSegura2026!")
    db.flush()
    token = crear_token(asistente)

    r = cliente.post(f"{ASISTENTES_URL}/{asistente.id}/desactivar", headers=auth_headers(gerente))

    assert r.status_code == 200, r.text
    datos = r.json()
    assert datos["asistente"]["estado"] == "inactiva"
    assert datos["sesiones_cerradas"] is True
    assert TipoEvento.SESION_CERRADA in tipos_para(publicados, asistente)
    sesion = cliente.get(PERFIL_URL, headers={"Authorization": f"Bearer {token}"})
    assert sesion.status_code == 401
    login = cliente.post(
        LOGIN_URL, json={"username": asistente.username, "contrasena": "ClaveSegura2026!"}
    )
    assert login.status_code in (401, 403)

    # CA11: se puede reactivar después.
    reactivada = cliente.post(
        f"{ASISTENTES_URL}/{asistente.id}/activar", headers=auth_headers(gerente)
    )
    assert reactivada.status_code == 200
    assert acciones_de(db, asistente) == ["desactivada", "activada"]
    login = cliente.post(
        LOGIN_URL, json={"username": asistente.username, "contrasena": "ClaveSegura2026!"}
    )
    assert login.status_code == 200


def test_ca12_ca14_desactivar_la_unica_activa_avisa_y_cancela_ordenes(
    cliente: TestClient, dos_gerentes: DosGerentes, db: Session, publicados: Publicados
) -> None:
    gerente = dos_gerentes.uno.gerente
    asistente = dos_gerentes.uno.asistente
    enviada = nueva_orden(db, nueva_deuda(db, gerente), "enviada", asistente=asistente)
    vista = nueva_orden(db, nueva_deuda(db, gerente), "vista", asistente=asistente)
    aceptada = nueva_orden(db, nueva_deuda(db, gerente), "aceptada", asistente=asistente)

    r = cliente.post(f"{ASISTENTES_URL}/{asistente.id}/desactivar", headers=auth_headers(gerente))

    assert r.status_code == 200, r.text
    datos = r.json()
    assert datos["sin_asistente_activa"] is True
    assert "tú harás los pagos" in datos["aviso"]
    assert set(datos["ordenes_canceladas"]) == {str(enviada.id), str(vista.id)}
    for orden in (enviada, vista, aceptada):
        db.refresh(orden)
    assert enviada.estado == vista.estado == "cancelada"
    assert enviada.cancelada_en is not None
    assert aceptada.estado == "aceptada"
    assert tipos_para(publicados, asistente).count(TipoEvento.ORDEN_CANCELADA) == 2

    avisos = db.scalars(select(Notificacion).where(Notificacion.usuario_id == gerente.id)).all()
    assert len(avisos) == 1
    assert "2 órdenes urgentes" in avisos[0].mensaje


def test_ca12_desactivar_sin_ordenes_no_notifica_y_repetir_no_cambia_nada(
    cliente: TestClient, dos_gerentes: DosGerentes, db: Session
) -> None:
    gerente = dos_gerentes.uno.gerente
    asistente = dos_gerentes.uno.asistente
    url = f"{ASISTENTES_URL}/{asistente.id}/desactivar"

    primera = cliente.post(url, headers=auth_headers(gerente))
    db.refresh(asistente)
    version = asistente.token_version
    segunda = cliente.post(url, headers=auth_headers(gerente))

    assert primera.status_code == segunda.status_code == 200
    assert segunda.json()["sin_asistente_activa"] is True
    db.refresh(asistente)
    assert asistente.token_version == version
    assert acciones_de(db, asistente) == ["desactivada"]
    avisos = db.scalars(select(Notificacion).where(Notificacion.usuario_id == gerente.id)).all()
    assert avisos == []


def test_ca15_solo_se_elimina_una_cuenta_inactiva(
    cliente: TestClient, dos_gerentes: DosGerentes, db: Session
) -> None:
    gerente = dos_gerentes.uno.gerente
    activa = dos_gerentes.uno.asistente

    r = cliente.delete(f"{ASISTENTES_URL}/{activa.id}", headers=auth_headers(gerente))

    assert r.status_code == 409
    assert r.json()["code"] == "CUENTA_ACTIVA"
    db.refresh(activa)
    assert activa.eliminado_en is None


def test_ca15_eliminar_conserva_el_nombre_en_el_historial(
    cliente: TestClient, dos_gerentes: DosGerentes, db: Session
) -> None:
    gerente = dos_gerentes.uno.gerente
    inactiva = nueva_asistente(db, gerente, "Marta")

    r = cliente.delete(f"{ASISTENTES_URL}/{inactiva.id}", headers=auth_headers(gerente))

    assert r.status_code == 204, r.text
    db.refresh(inactiva)
    assert inactiva.eliminado_en is not None
    assert acciones_de(db, inactiva) == ["eliminada"]
    registro = db.scalar(
        select(Auditoria).where(
            Auditoria.accion == "cuenta_eliminada", Auditoria.entidad_id == inactiva.id
        )
    )
    assert registro is not None
    assert registro.detalle["nombre"] == "Marta Prueba"

    # Una cuenta eliminada ya no se puede activar, eliminar ni restablecer.
    for metodo, ruta in (
        ("post", f"{inactiva.id}/activar"),
        ("delete", f"{inactiva.id}"),
        ("post", f"{inactiva.id}/restablecer-contrasena"),
    ):
        respuesta = cliente.request(
            metodo, f"{ASISTENTES_URL}/{ruta}", headers=auth_headers(gerente)
        )
        assert respuesta.status_code == 404


def test_ca16_restablecer_genera_contrasena_inicial_y_cierra_sesiones(
    cliente: TestClient, dos_gerentes: DosGerentes, db: Session, publicados: Publicados
) -> None:
    gerente = dos_gerentes.uno.gerente
    asistente = dos_gerentes.uno.asistente
    asistente.contrasena_inicial = False
    asistente.intentos_fallidos = 3
    db.flush()
    token = crear_token(asistente)

    r = cliente.post(
        f"{ASISTENTES_URL}/{asistente.id}/restablecer-contrasena", headers=auth_headers(gerente)
    )

    assert r.status_code == 200, r.text
    datos = r.json()
    assert datos["username"] == asistente.username
    assert datos["contrasena_inicial"] is True
    assert len(datos["contrasena"]) >= 12
    db.refresh(asistente)
    assert verificar_contrasena(datos["contrasena"], asistente.password_hash)
    assert asistente.intentos_fallidos == 0
    historial = db.scalars(
        select(HistorialContrasena).where(HistorialContrasena.usuario_id == asistente.id)
    ).all()
    assert len(historial) == 1
    assert TipoEvento.SESION_CERRADA in tipos_para(publicados, asistente)
    assert cliente.get(PERFIL_URL, headers={"Authorization": f"Bearer {token}"}).status_code == 401

    registro = db.scalar(select(Auditoria).where(Auditoria.accion == "contrasena_restablecida"))
    assert registro is not None
    assert "contrasena" not in str(registro.detalle)

    login = cliente.post(
        LOGIN_URL, json={"username": asistente.username, "contrasena": datos["contrasena"]}
    )
    assert login.status_code == 200


@pytest.mark.parametrize(
    ("metodo", "ruta"),
    [
        ("post", "activar"),
        ("post", "desactivar"),
        ("post", "restablecer-contrasena"),
        ("delete", ""),
    ],
)
def test_otro_gerente_no_ve_la_cuenta_y_la_asistente_no_tiene_permiso(
    cliente: TestClient, dos_gerentes: DosGerentes, db: Session, metodo: str, ruta: str
) -> None:
    ajena = nueva_asistente(db, dos_gerentes.dos.gerente, "Ajena")
    url = f"{ASISTENTES_URL}/{ajena.id}/{ruta}".rstrip("/")

    del_otro = cliente.request(metodo, url, headers=auth_headers(dos_gerentes.uno.gerente))
    de_asistente = cliente.request(metodo, url, headers=auth_headers(dos_gerentes.dos.asistente))

    assert del_otro.status_code == 404
    assert de_asistente.status_code == 403
    db.refresh(ajena)
    assert ajena.estado == "inactiva"
    assert ajena.eliminado_en is None


def test_activaciones_simultaneas_dejan_una_sola_activa() -> None:
    """Dos activaciones a la vez del mismo gerente se hacen en fila y no chocan con el índice."""
    marca = uuid.uuid4().hex[:8]
    with SessionLocal() as sesion:
        gerente = Usuario(rol="gerente", username=f"g_activa_{marca}", password_hash="x")
        sesion.add(gerente)
        sesion.flush()
        cuentas = [
            Usuario(
                rol="asistente",
                gerente_id=gerente.id,
                username=f"a{indice}_{marca}",
                password_hash="x",
                estado="activa" if indice == 0 else "inactiva",
            )
            for indice in range(3)
        ]
        sesion.add_all(cuentas)
        sesion.commit()
        gerente_id = gerente.id
        candidatas = [cuenta.id for cuenta in cuentas[1:]]

    def activar_en_hilo(asistente_id: uuid.UUID) -> None:
        with SessionLocal() as sesion_hilo:
            propio = sesion_hilo.get_one(Usuario, gerente_id)
            activar_asistente(
                sesion_hilo, propio, asistente_id, Origen(dispositivo="pytest", ip=None)
            )

    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            list(executor.map(activar_en_hilo, candidatas))

        with SessionLocal() as sesion:
            activas = sesion.scalars(
                select(Usuario.id).where(
                    Usuario.gerente_id == gerente_id, Usuario.estado == "activa"
                )
            ).all()
            assert len(activas) == 1
            assert activas[0] in candidatas
            historial = sesion.scalars(
                select(ActivacionCuenta.accion).where(ActivacionCuenta.realizada_por == gerente_id)
            ).all()
            assert sorted(historial) == ["activada", "activada", "desactivada", "desactivada"]
    finally:
        with SessionLocal() as sesion:
            parametros = {"gid": gerente_id}
            sesion.execute(
                text("DELETE FROM activacion_cuenta WHERE realizada_por = :gid"), parametros
            )
            sesion.execute(text("DELETE FROM auditoria WHERE gerente_id = :gid"), parametros)
            sesion.execute(text("DELETE FROM usuario WHERE gerente_id = :gid"), parametros)
            sesion.execute(text("DELETE FROM usuario WHERE id = :gid"), parametros)
            sesion.commit()
