"""Consulta y reemplazo de comprobantes (H24 CA08, TASK-84).

El reemplazo crea una versión nueva vinculada por reemplaza_a_id y conserva la rechazada.
"""

import uuid
from collections.abc import Iterator
from typing import Any

import pytest
from celery.canvas import Signature
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.main import app
from app.models import Auditoria, Comprobante, ComprobanteDeuda, Deuda, Usuario
from tests.conftest import DosGerentes, Equipo, S3EnMemoria
from tests.test_api_comprobantes import cabecera, en_proceso, subir
from tests.test_archivos import imagen, pdf

RUTA = "/api/v1/comprobantes"


@pytest.fixture(autouse=True)
def sin_cola(enviadas: list[Signature]) -> list[Signature]:
    """Ninguna subida de estas pruebas llega a Redis."""
    return enviadas


@pytest.fixture
def cliente(db: Session) -> Iterator[TestClient]:
    app.dependency_overrides[get_db] = lambda: db
    yield TestClient(app)
    app.dependency_overrides.clear()


def rechazado(cliente: TestClient, db: Session, equipo: Equipo) -> Comprobante:
    """Comprobante subido y luego rechazado; su deuda vuelve a tener el intento vigente."""
    deuda = en_proceso(db, equipo, "75.00")
    r = subir(cliente, equipo.asistente, [{"deuda_id": str(deuda.id)}])
    comprobante = db.get(Comprobante, uuid.UUID(r.json()["id"]))
    assert comprobante is not None
    comprobante.estado = "rechazado"
    comprobante.motivo_codigo = "ilegible"
    deuda.estado = "en_proceso"
    db.flush()
    return comprobante


def deuda_de(db: Session, comprobante: Comprobante) -> Deuda:
    reparto = db.scalar(
        select(ComprobanteDeuda).where(ComprobanteDeuda.comprobante_id == comprobante.id)
    )
    assert reparto is not None
    deuda = db.get(Deuda, reparto.deuda_id)
    assert deuda is not None
    return deuda


def reemplazar(
    cliente: TestClient, usuario: Usuario, comprobante_id: uuid.UUID, contenido: bytes
) -> Any:
    return cliente.put(
        f"{RUTA}/{comprobante_id}/archivo",
        headers=cabecera(usuario),
        files={"archivo": ("nuevo.pdf", contenido, "application/pdf")},
    )


def test_consulta_el_estado_con_su_reparto_y_un_enlace_firmado(
    cliente: TestClient, db: Session, dos_gerentes: DosGerentes, s3: S3EnMemoria
) -> None:
    equipo = dos_gerentes.uno
    deuda = en_proceso(db, equipo, "40.00")
    subido = subir(cliente, equipo.asistente, [{"deuda_id": str(deuda.id)}]).json()

    # El gerente ve el comprobante de su asistente, y ella también.
    for usuario in (equipo.gerente, equipo.asistente):
        r = cliente.get(f"{RUTA}/{subido['id']}", headers=cabecera(usuario))
        assert r.status_code == 200
        cuerpo = r.json()
        assert (cuerpo["estado"], cuerpo["motivo_codigo"], cuerpo["reemplazado_por_id"]) == (
            "procesando",
            None,
            None,
        )
        assert cuerpo["deudas"] == [{"deuda_id": str(deuda.id), "monto_aplicado": "40.00"}]
        ruta = f"comprobantes/{equipo.gerente.id}/{subido['id']}.png"
        assert cuerpo["archivo_enlace"] == f"https://s3.local/{ruta}?expira=300"


def test_el_comprobante_de_otro_gerente_responde_404(
    cliente: TestClient, db: Session, dos_gerentes: DosGerentes, s3: S3EnMemoria
) -> None:
    ajena = en_proceso(db, dos_gerentes.dos)
    subido = subir(cliente, dos_gerentes.dos.asistente, [{"deuda_id": str(ajena.id)}]).json()

    for ruta in (subido["id"], str(uuid.uuid4())):
        r = cliente.get(f"{RUTA}/{ruta}", headers=cabecera(dos_gerentes.uno.gerente))
        assert (r.status_code, r.json()["code"]) == (404, "NO_ENCONTRADO")


def test_reemplaza_un_comprobante_rechazado_y_conserva_el_anterior(
    cliente: TestClient, db: Session, dos_gerentes: DosGerentes, s3: S3EnMemoria
) -> None:
    equipo = dos_gerentes.uno
    anterior = rechazado(cliente, db, equipo)

    r = reemplazar(cliente, equipo.asistente, anterior.id, pdf())

    assert r.status_code == 201, r.json()
    nuevo = r.json()
    assert (nuevo["estado"], nuevo["archivo_tipo"], nuevo["reemplaza_a_id"]) == (
        "procesando",
        "pdf",
        str(anterior.id),
    )
    deuda = deuda_de(db, anterior)
    assert nuevo["deudas"] == [{"deuda_id": str(deuda.id), "monto_aplicado": "75.00"}]
    db.refresh(deuda)
    assert deuda.estado == "por_validar"
    db.refresh(anterior)
    assert (anterior.estado, anterior.motivo_codigo) == ("rechazado", "ilegible")
    assert len(s3.objetos) == 2
    historial = cliente.get(f"{RUTA}/{anterior.id}", headers=cabecera(equipo.gerente)).json()
    assert historial["reemplazado_por_id"] == nuevo["id"]
    auditoria = db.scalar(select(Auditoria).where(Auditoria.entidad_id == uuid.UUID(nuevo["id"])))
    assert auditoria is not None and auditoria.accion == "comprobante_reemplazado"


def test_un_comprobante_se_reemplaza_una_sola_vez(
    cliente: TestClient, db: Session, dos_gerentes: DosGerentes, s3: S3EnMemoria
) -> None:
    equipo = dos_gerentes.uno
    anterior = rechazado(cliente, db, equipo)
    assert reemplazar(cliente, equipo.asistente, anterior.id, pdf()).status_code == 201

    r = reemplazar(cliente, equipo.asistente, anterior.id, imagen("JPEG"))

    assert (r.status_code, r.json()["code"]) == (409, "YA_REEMPLAZADO")
    assert len(s3.objetos) == 2


def test_el_gerente_no_reemplaza_vouchers(
    cliente: TestClient, db: Session, dos_gerentes: DosGerentes, s3: S3EnMemoria
) -> None:
    equipo = dos_gerentes.uno
    anterior = rechazado(cliente, db, equipo)

    r = reemplazar(cliente, equipo.gerente, anterior.id, pdf())

    assert (r.status_code, r.json()["code"]) == (403, "SIN_PERMISO")
    assert len(s3.objetos) == 1


def test_solo_se_reemplaza_un_comprobante_rechazado(
    cliente: TestClient, db: Session, dos_gerentes: DosGerentes, s3: S3EnMemoria
) -> None:
    equipo = dos_gerentes.uno
    deuda = en_proceso(db, equipo)
    subido = subir(cliente, equipo.asistente, [{"deuda_id": str(deuda.id)}]).json()

    r = reemplazar(cliente, equipo.asistente, uuid.UUID(subido["id"]), pdf())

    assert (r.status_code, r.json()["code"]) == (409, "ESTADO_NO_PERMITIDO")


def test_no_se_reemplaza_el_comprobante_de_otro_gerente(
    cliente: TestClient, db: Session, dos_gerentes: DosGerentes, s3: S3EnMemoria
) -> None:
    ajeno = rechazado(cliente, db, dos_gerentes.dos)

    r = reemplazar(cliente, dos_gerentes.uno.asistente, ajeno.id, pdf())

    assert (r.status_code, r.json()["code"]) == (404, "NO_ENCONTRADO")
    assert len(s3.objetos) == 1


def test_el_reemplazo_vuelve_a_validar_el_estado_de_la_deuda(
    cliente: TestClient, db: Session, dos_gerentes: DosGerentes, s3: S3EnMemoria
) -> None:
    equipo = dos_gerentes.uno
    anterior = rechazado(cliente, db, equipo)
    deuda = deuda_de(db, anterior)
    deuda.estado = "anulada"
    db.flush()

    r = reemplazar(cliente, equipo.asistente, anterior.id, pdf())

    assert (r.status_code, r.json()["code"]) == (409, "ESTADO_NO_PERMITIDO")
    assert len(s3.objetos) == 1
