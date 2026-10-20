"""API de solicitudes de aprobación (H05, TASK-24): lista, aprobar y rechazar.

CA07: el gerente aprueba o rechaza desde la app. CA08: motivo opcional y aviso a la asistente.
CA10: lista por estado. CA12: la aprobación autoriza solo ese importe y esa moneda.
"""

import uuid
from collections.abc import Iterator
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencias import Origen
from app.core.seguridad import crear_token
from app.main import app
from app.models import Auditoria, Deuda, Notificacion, Servicio, SolicitudAprobacion, Usuario
from app.services.limites import fijar_limite
from app.services.pagos import ResultadoInicio, iniciar_pago
from tests.conftest import DosGerentes, Equipo, nueva_deuda, nuevo_comprobante

URL = "/api/v1/solicitudes"
ORIGEN = Origen(dispositivo="pruebas", ip=None)


@pytest.fixture
def cliente(db: Session) -> Iterator[TestClient]:
    # Sin with: no arranca el ciclo de vida, que se suscribe a Redis y estas rutas no usan.
    app.dependency_overrides[get_db] = lambda: db
    yield TestClient(app)
    app.dependency_overrides.clear()


def cabecera(usuario: Usuario) -> dict[str, str]:
    return {"Authorization": f"Bearer {crear_token(usuario)}"}


def pedir_aprobacion(db: Session, equipo: Equipo, monto: str = "250.00") -> Deuda:
    """Deuda sobre el límite por pago de 100: la asistente la inicia y queda esperando."""
    fijar_limite(db, equipo.gerente.id, por_pago=Decimal("100.00"))
    deuda = nueva_deuda(db, equipo.gerente, monto=monto)
    servicio = db.get_one(Servicio, deuda.servicio_id)
    servicio.alias = "Luz del departamento"
    equipo.asistente.nombres, equipo.asistente.apellidos = "Rosa", "Melgar"
    db.flush()
    inicio = iniciar_pago(db, equipo.asistente, deuda.id, origen=ORIGEN)
    assert inicio.resultado == ResultadoInicio.REQUIERE_APROBACION
    return deuda


def solicitud_de(db: Session, deuda: Deuda) -> SolicitudAprobacion:
    solicitud = db.scalars(
        select(SolicitudAprobacion)
        .where(SolicitudAprobacion.deuda_id == deuda.id)
        .order_by(SolicitudAprobacion.creado_en.desc())
    ).first()
    assert solicitud is not None
    return solicitud


def avisos_a(db: Session, usuario: Usuario) -> list[Notificacion]:
    return list(
        db.scalars(
            select(Notificacion)
            .where(Notificacion.usuario_id == usuario.id)
            .order_by(Notificacion.creado_en, Notificacion.id)
        )
    )


def auditorias(db: Session, accion: str) -> int:
    consulta = select(func.count()).select_from(Auditoria).where(Auditoria.accion == accion)
    return db.scalar(consulta) or 0


def test_la_lista_trae_el_contexto_y_filtra_por_estado(
    cliente: TestClient, db: Session, dos_gerentes: DosGerentes
) -> None:
    equipo = dos_gerentes.uno
    pendiente = pedir_aprobacion(db, equipo)
    aprobada = pedir_aprobacion(db, equipo, monto="180.00")
    cliente.post(f"{URL}/{solicitud_de(db, aprobada).id}/aprobar", headers=cabecera(equipo.gerente))
    # La del otro gerente nunca aparece.
    pedir_aprobacion(db, dos_gerentes.dos)

    todas = cliente.get(URL, headers=cabecera(equipo.gerente)).json()
    assert todas["total"] == 2
    solo_pendientes = cliente.get(
        URL, params={"estado": "pendiente"}, headers=cabecera(equipo.gerente)
    ).json()

    assert solo_pendientes["total"] == 1
    fila = solo_pendientes["items"][0]
    assert fila["deuda_id"] == str(pendiente.id)
    assert (fila["servicio"], fila["asistente"], fila["monto"], fila["moneda"]) == (
        "Luz del departamento",
        "Rosa Melgar",
        "250.00",
        "PEN",
    )
    assert fila["fecha_vencimiento"] == pendiente.fecha_vencimiento.isoformat()
    assert fila["resuelta_por_nombre"] is None

    resueltas = cliente.get(
        URL, params={"estado": "aprobada"}, headers=cabecera(equipo.gerente)
    ).json()
    assert resueltas["items"][0]["resuelta_por_nombre"] == equipo.gerente.username


def test_la_lista_valida_el_estado_y_es_solo_del_gerente(
    cliente: TestClient, dos_gerentes: DosGerentes
) -> None:
    r = cliente.get(URL, params={"estado": "otra"}, headers=cabecera(dos_gerentes.uno.gerente))
    assert r.status_code == 422
    r = cliente.get(URL, headers=cabecera(dos_gerentes.uno.asistente))
    assert (r.status_code, r.json()["code"]) == (403, "SIN_PERMISO")


def test_aprobar_autoriza_el_pago_y_avisa_a_la_asistente(
    cliente: TestClient, db: Session, dos_gerentes: DosGerentes
) -> None:
    equipo = dos_gerentes.uno
    deuda = pedir_aprobacion(db, equipo)
    solicitud = solicitud_de(db, deuda)

    r = cliente.post(f"{URL}/{solicitud.id}/aprobar", headers=cabecera(equipo.gerente))

    assert r.status_code == 200
    assert (r.json()["estado"], r.json()["resuelta_por"]) == ("aprobada", str(equipo.gerente.id))
    db.refresh(deuda)
    # Aprobar no inicia ni paga: la deuda vuelve a pendiente y la asistente la inicia.
    assert deuda.estado == "pendiente"
    aviso = avisos_a(db, equipo.asistente)[-1]
    assert aviso.titulo == "Pago aprobado"
    assert "PEN 250.00 de Luz del departamento" in aviso.mensaje
    assert auditorias(db, "aprobacion_aprobada") == 1

    inicio = iniciar_pago(db, equipo.asistente, deuda.id, origen=ORIGEN)
    assert inicio.resultado == ResultadoInicio.INICIADO


def test_repetir_la_misma_decision_no_duplica_efectos(
    cliente: TestClient, db: Session, dos_gerentes: DosGerentes
) -> None:
    equipo = dos_gerentes.uno
    solicitud = solicitud_de(db, pedir_aprobacion(db, equipo))
    ruta = f"{URL}/{solicitud.id}/aprobar"

    primera = cliente.post(ruta, headers=cabecera(equipo.gerente))
    segunda = cliente.post(ruta, headers=cabecera(equipo.gerente))

    assert segunda.status_code == 200
    assert segunda.json()["resuelta_en"] == primera.json()["resuelta_en"]
    assert len(avisos_a(db, equipo.asistente)) == 1
    assert auditorias(db, "aprobacion_aprobada") == 1
    contraria = cliente.post(f"{URL}/{solicitud.id}/rechazar", headers=cabecera(equipo.gerente))
    assert (contraria.status_code, contraria.json()["code"]) == (409, "SOLICITUD_YA_RESUELTA")


def test_la_aprobacion_solo_vale_para_ese_importe(
    cliente: TestClient, db: Session, dos_gerentes: DosGerentes
) -> None:
    equipo = dos_gerentes.uno
    deuda = pedir_aprobacion(db, equipo)
    cliente.post(f"{URL}/{solicitud_de(db, deuda).id}/aprobar", headers=cabecera(equipo.gerente))

    deuda.monto = Decimal("300.00")
    db.flush()
    inicio = iniciar_pago(db, equipo.asistente, deuda.id, origen=ORIGEN)

    assert inicio.resultado == ResultadoInicio.REQUIERE_APROBACION
    assert inicio.solicitud is not None
    assert inicio.solicitud.monto == Decimal("300.00")


def test_rechazar_guarda_el_motivo_y_avisa_a_la_asistente(
    cliente: TestClient, db: Session, dos_gerentes: DosGerentes
) -> None:
    equipo = dos_gerentes.uno
    deuda = pedir_aprobacion(db, equipo)
    solicitud = solicitud_de(db, deuda)

    r = cliente.post(
        f"{URL}/{solicitud.id}/rechazar",
        json={"motivo": "  Ya lo pagué yo  "},
        headers=cabecera(equipo.gerente),
    )

    assert r.status_code == 200
    assert (r.json()["estado"], r.json()["motivo"]) == ("rechazada", "Ya lo pagué yo")
    db.refresh(deuda)
    assert deuda.estado == "pendiente"
    aviso = avisos_a(db, equipo.asistente)[-1]
    assert aviso.titulo == "Solicitud rechazada"
    assert aviso.mensaje.endswith("Motivo: Ya lo pagué yo")
    assert auditorias(db, "aprobacion_rechazada") == 1


def test_rechazar_sin_motivo_y_motivo_demasiado_largo(
    cliente: TestClient, db: Session, dos_gerentes: DosGerentes
) -> None:
    equipo = dos_gerentes.uno
    solicitud = solicitud_de(db, pedir_aprobacion(db, equipo))
    ruta = f"{URL}/{solicitud.id}/rechazar"

    largo = cliente.post(ruta, json={"motivo": "x" * 301}, headers=cabecera(equipo.gerente))
    assert largo.status_code == 422
    sin_cuerpo = cliente.post(ruta, headers=cabecera(equipo.gerente))
    assert (sin_cuerpo.status_code, sin_cuerpo.json()["motivo"]) == (200, None)
    assert "Motivo" not in avisos_a(db, equipo.asistente)[-1].mensaje


def test_con_abonos_la_deuda_vuelve_a_pagada_parcial(
    cliente: TestClient, db: Session, dos_gerentes: DosGerentes
) -> None:
    equipo = dos_gerentes.uno
    fijar_limite(db, equipo.gerente.id, por_pago=Decimal("100.00"))
    deuda = nueva_deuda(db, equipo.gerente, monto="400.00", estado="pagada_parcial")
    nuevo_comprobante(db, deuda, equipo.asistente, "150.00")
    iniciar_pago(db, equipo.asistente, deuda.id, origen=ORIGEN)

    cliente.post(f"{URL}/{solicitud_de(db, deuda).id}/rechazar", headers=cabecera(equipo.gerente))

    db.refresh(deuda)
    assert deuda.estado == "pagada_parcial"


def test_una_solicitud_inexistente_responde_404(
    cliente: TestClient, dos_gerentes: DosGerentes
) -> None:
    r = cliente.post(f"{URL}/{uuid.uuid4()}/aprobar", headers=cabecera(dos_gerentes.uno.gerente))
    assert (r.status_code, r.json()["code"]) == (404, "NO_ENCONTRADO")
