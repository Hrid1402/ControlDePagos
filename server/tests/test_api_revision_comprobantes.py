"""Revisión de comprobantes por el gerente (H24 CA07, TASK-88).

Aprobar o rechazar una sola vez, con el saldo vuelto a calcular con bloqueo, y auditoría y avisos
después del commit.
"""

import uuid
from collections.abc import Iterator
from datetime import date
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.eventos import Evento
from app.main import app
from app.models import Auditoria, Comprobante, ComprobanteDeuda, Deuda, Notificacion, Usuario
from app.services.saldo import saldo_de
from tests.conftest import DosGerentes, Equipo
from tests.test_api_comprobantes import cabecera
from tests.test_validacion_abonos import comprobante_de, deuda_de

RUTA = "/api/v1/comprobantes"


@pytest.fixture
def cliente(db: Session) -> Iterator[TestClient]:
    app.dependency_overrides[get_db] = lambda: db
    yield TestClient(app)
    app.dependency_overrides.clear()


def en_revision(
    db: Session,
    equipo: Equipo,
    repartos: list[tuple[Deuda, str]] | None = None,
    monto: str | None = "100.00",
    motivo: str | None = "monto_mayor",
) -> Comprobante:
    if repartos is None:
        repartos = [(deuda_de(db, equipo.gerente), "85.40")]
    comprobante = comprobante_de(db, equipo, repartos, estado="en_revision")
    comprobante.monto = Decimal(monto) if monto else None
    comprobante.motivo_codigo = motivo
    db.flush()
    return comprobante


def aprobar(
    cliente: TestClient, usuario: Usuario, comprobante_id: uuid.UUID, cuerpo: Any = None
) -> Any:
    return cliente.post(f"{RUTA}/{comprobante_id}/aprobar", headers=cabecera(usuario), json=cuerpo)


def rechazar(
    cliente: TestClient, usuario: Usuario, comprobante_id: uuid.UUID, motivo: str = "Ilegible"
) -> Any:
    return cliente.post(
        f"{RUTA}/{comprobante_id}/rechazar",
        headers=cabecera(usuario),
        json={"motivo": motivo},
    )


def eventos_de(db: Session, comprobante: Comprobante) -> list[str]:
    return list(
        db.scalars(
            select(Auditoria.accion)
            .where(Auditoria.entidad_id == comprobante.id)
            .order_by(Auditoria.creado_en)
        )
    )


def test_el_gerente_aprueba_y_la_deuda_queda_pagada(
    cliente: TestClient,
    db: Session,
    dos_gerentes: DosGerentes,
    s3: object,
    publicados: list[tuple[uuid.UUID, Evento]],
) -> None:
    equipo = dos_gerentes.uno
    comprobante = en_revision(db, equipo)
    (deuda_id,) = db.scalars(
        select(ComprobanteDeuda.deuda_id).where(ComprobanteDeuda.comprobante_id == comprobante.id)
    )

    r = aprobar(cliente, equipo.gerente, comprobante.id)

    assert r.status_code == 200, r.json()
    cuerpo = r.json()
    assert (cuerpo["estado"], cuerpo["observacion"]) == (
        "validado",
        "El gerente aprobó el comprobante.",
    )
    assert cuerpo["revisado_en"] is not None
    db.refresh(comprobante)
    assert comprobante.revisado_por == equipo.gerente.id
    deuda = db.get(Deuda, deuda_id)
    assert deuda is not None
    assert (deuda.estado, saldo_de(db, deuda)) == ("pagada", Decimal("0.00"))
    assert eventos_de(db, comprobante) == ["comprobante_aprobado"]
    assert (
        db.scalar(
            select(func.count())
            .select_from(Notificacion)
            .where(Notificacion.tipo == "deuda_pagada")
        )
        == 1
    )
    resultado = [u for u, e in publicados if e.tipo == "comprobante_resultado"]
    assert resultado == [equipo.asistente.id, equipo.gerente.id]


def test_aprobar_dos_veces_aplica_el_abono_una_sola_vez(
    cliente: TestClient, db: Session, dos_gerentes: DosGerentes, s3: object
) -> None:
    equipo = dos_gerentes.uno
    comprobante = en_revision(db, equipo)

    primero = aprobar(cliente, equipo.gerente, comprobante.id)
    segundo = aprobar(cliente, equipo.gerente, comprobante.id)

    assert (primero.status_code, segundo.status_code) == (200, 200)
    assert segundo.json()["revisado_en"] == primero.json()["revisado_en"]
    assert eventos_de(db, comprobante) == ["comprobante_aprobado"]


def test_el_gerente_corrige_el_reparto_de_un_monto_menor(
    cliente: TestClient, db: Session, dos_gerentes: DosGerentes, s3: object
) -> None:
    equipo = dos_gerentes.uno
    luz = deuda_de(db, equipo.gerente, monto="60.00")
    agua = deuda_de(db, equipo.gerente, monto="25.40", periodo=date(2026, 9, 1))
    comprobante = en_revision(
        db, equipo, [(luz, "60.00"), (agua, "25.40")], monto="70.00", motivo="monto_menor"
    )
    reparto = [
        {"deuda_id": str(luz.id), "monto_aplicado": "60.00"},
        {"deuda_id": str(agua.id), "monto_aplicado": "10.00"},
    ]

    r = aprobar(cliente, equipo.gerente, comprobante.id, {"deudas": reparto})

    assert r.status_code == 200, r.json()
    assert sorted(r.json()["deudas"], key=lambda d: d["monto_aplicado"]) == sorted(
        reparto, key=lambda d: d["monto_aplicado"]
    )
    db.refresh(luz)
    db.refresh(agua)
    assert (luz.estado, agua.estado) == ("pagada", "pagada_parcial")
    assert saldo_de(db, agua) == Decimal("15.40")


def test_el_reparto_no_supera_el_monto_del_comprobante(
    cliente: TestClient, db: Session, dos_gerentes: DosGerentes, s3: object
) -> None:
    equipo = dos_gerentes.uno
    deuda = deuda_de(db, equipo.gerente)
    comprobante = en_revision(db, equipo, [(deuda, "85.40")], monto="80.00", motivo="monto_menor")

    r = aprobar(
        cliente,
        equipo.gerente,
        comprobante.id,
        {"deudas": [{"deuda_id": str(deuda.id), "monto_aplicado": "85.40"}]},
    )

    assert (r.status_code, r.json()["field"]) == (422, "deudas")
    assert "PEN 80.00" in r.json()["detail"]
    db.refresh(comprobante)
    assert comprobante.estado == "en_revision"


def test_el_reparto_corregido_tiene_las_mismas_deudas(
    cliente: TestClient, db: Session, dos_gerentes: DosGerentes, s3: object
) -> None:
    equipo = dos_gerentes.uno
    comprobante = en_revision(db, equipo)
    otra = deuda_de(db, equipo.gerente, periodo=date(2026, 9, 1))

    r = aprobar(
        cliente,
        equipo.gerente,
        comprobante.id,
        {"deudas": [{"deuda_id": str(otra.id), "monto_aplicado": "10.00"}]},
    )

    assert (r.status_code, r.json()["code"]) == (422, "VALIDACION")


def test_si_otro_comprobante_cubrio_el_saldo_la_aprobacion_responde_409(
    cliente: TestClient, db: Session, dos_gerentes: DosGerentes, s3: object
) -> None:
    equipo = dos_gerentes.uno
    deuda = deuda_de(db, equipo.gerente)
    comprobante = en_revision(db, equipo, [(deuda, "85.40")])
    comprobante_de(db, equipo, [(deuda, "40.00")], estado="validado")

    r = aprobar(cliente, equipo.gerente, comprobante.id)

    assert (r.status_code, r.json()["code"], r.json()["deuda_id"]) == (
        409,
        "SIN_SALDO",
        str(deuda.id),
    )
    db.refresh(comprobante)
    assert comprobante.estado == "en_revision"


def test_el_gerente_rechaza_con_su_motivo_y_la_deuda_vuelve_al_intento(
    cliente: TestClient, db: Session, dos_gerentes: DosGerentes, s3: object
) -> None:
    equipo = dos_gerentes.uno
    deuda = deuda_de(db, equipo.gerente)
    comprobante = en_revision(db, equipo, [(deuda, "85.40")])

    r = rechazar(cliente, equipo.gerente, comprobante.id, "  No es de esta   deuda ")

    assert r.status_code == 200, r.json()
    assert (r.json()["estado"], r.json()["motivo_codigo"]) == ("rechazado", "monto_mayor")
    assert r.json()["observacion"] == "El gerente rechazó el comprobante: No es de esta deuda"
    db.refresh(deuda)
    assert deuda.estado == "en_proceso"
    aviso = db.scalar(select(Notificacion).where(Notificacion.tipo == "comprobante_rechazado"))
    assert aviso is not None and aviso.usuario_id == equipo.asistente.id
    assert eventos_de(db, comprobante) == ["comprobante_rechazado"]
    auditoria = db.scalar(select(Auditoria).where(Auditoria.entidad_id == comprobante.id))
    assert auditoria is not None and auditoria.detalle["motivo"] == "No es de esta deuda"

    repetido = rechazar(cliente, equipo.gerente, comprobante.id)
    assert repetido.status_code == 200
    assert eventos_de(db, comprobante) == ["comprobante_rechazado"]


def test_la_decision_contraria_responde_409(
    cliente: TestClient, db: Session, dos_gerentes: DosGerentes, s3: object
) -> None:
    equipo = dos_gerentes.uno
    aprobado, rechazado = (
        en_revision(db, equipo),
        en_revision(
            db, equipo, [(deuda_de(db, equipo.gerente, periodo=date(2026, 9, 1)), "85.40")]
        ),
    )
    aprobar(cliente, equipo.gerente, aprobado.id)
    rechazar(cliente, equipo.gerente, rechazado.id)

    assert rechazar(cliente, equipo.gerente, aprobado.id).status_code == 409
    assert aprobar(cliente, equipo.gerente, rechazado.id).status_code == 409


@pytest.mark.parametrize(
    ("estado", "detalle"),
    [
        ("procesando", "El comprobante todavía se está validando. Espera el resultado."),
        ("validado", "El comprobante ya fue resuelto."),
    ],
)
def test_solo_se_decide_un_comprobante_en_revision(
    cliente: TestClient,
    db: Session,
    dos_gerentes: DosGerentes,
    s3: object,
    estado: str,
    detalle: str,
) -> None:
    equipo = dos_gerentes.uno
    comprobante = comprobante_de(db, equipo, [(deuda_de(db, equipo.gerente), "85.40")], estado)

    for respuesta in (
        aprobar(cliente, equipo.gerente, comprobante.id),
        rechazar(cliente, equipo.gerente, comprobante.id),
    ):
        assert (respuesta.status_code, respuesta.json()["detail"]) == (409, detalle)


def test_la_asistente_no_revisa_y_otro_gerente_no_ve_el_comprobante(
    cliente: TestClient, db: Session, dos_gerentes: DosGerentes, s3: object
) -> None:
    comprobante = en_revision(db, dos_gerentes.uno)

    for respuesta in (
        aprobar(cliente, dos_gerentes.uno.asistente, comprobante.id),
        rechazar(cliente, dos_gerentes.uno.asistente, comprobante.id),
    ):
        assert (respuesta.status_code, respuesta.json()["code"]) == (403, "SIN_PERMISO")
    for respuesta in (
        aprobar(cliente, dos_gerentes.dos.gerente, comprobante.id),
        rechazar(cliente, dos_gerentes.dos.gerente, comprobante.id),
        aprobar(cliente, dos_gerentes.uno.gerente, uuid.uuid4()),
    ):
        assert (respuesta.status_code, respuesta.json()["code"]) == (404, "NO_ENCONTRADO")
    db.refresh(comprobante)
    assert (comprobante.estado, comprobante.revisado_por) == ("en_revision", None)


@pytest.mark.parametrize("motivo", ["", "   ", "x" * 501])
def test_rechazar_exige_un_motivo_de_hasta_500_caracteres(
    cliente: TestClient, db: Session, dos_gerentes: DosGerentes, s3: object, motivo: str
) -> None:
    comprobante = en_revision(db, dos_gerentes.uno)

    r = rechazar(cliente, dos_gerentes.uno.gerente, comprobante.id, motivo)

    assert (r.status_code, r.json()["field"]) == (422, "motivo")
