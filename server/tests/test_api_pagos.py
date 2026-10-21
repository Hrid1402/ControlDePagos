import uuid
from collections.abc import Callable, Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.v1.pagos import deuda_salida
from app.core.database import get_db
from app.core.seguridad import crear_token
from app.main import app
from app.models import Limite, Usuario
from tests.conftest import DosGerentes, asistente_anterior, en_proceso_por, nueva_deuda


@pytest.fixture
def cliente(db: Session) -> Iterator[TestClient]:
    # Sin with: no arranca el ciclo de vida, que se suscribe a Redis y estas rutas no usan.
    app.dependency_overrides[get_db] = lambda: db
    yield TestClient(app)
    app.dependency_overrides.clear()


def cabecera(usuario: Usuario) -> dict[str, str]:
    return {"Authorization": f"Bearer {crear_token(usuario)}"}


def iniciar_ruta(deuda_id: uuid.UUID) -> str:
    return f"/api/v1/deudas/{deuda_id}/iniciar-pago"


def cancelar_ruta(deuda_id: uuid.UUID) -> str:
    return f"/api/v1/deudas/{deuda_id}/cancelar-inicio"


def test_iniciar_pago_marca_la_deuda_en_proceso(
    cliente: TestClient, db: Session, dos_gerentes: DosGerentes
) -> None:
    equipo = dos_gerentes.uno
    deuda = nueva_deuda(db, equipo.gerente, monto="85.40")

    r = cliente.post(iniciar_ruta(deuda.id), headers=cabecera(equipo.asistente))

    assert r.status_code == 200
    cuerpo = r.json()
    assert (cuerpo["resultado"], cuerpo["repetido"], cuerpo["solicitud_id"]) == (
        "iniciado",
        False,
        None,
    )
    assert cuerpo["deuda"]["estado"] == "en_proceso"
    assert cuerpo["deuda"]["saldo"] == "85.40"
    assert cuerpo["deuda"]["pago_iniciado_por"] == str(equipo.asistente.id)

    repetido = cliente.post(iniciar_ruta(deuda.id), headers=cabecera(equipo.asistente))
    assert repetido.status_code == 200
    assert repetido.json()["repetido"] is True


def test_superar_el_limite_responde_200_con_la_solicitud(
    cliente: TestClient, db: Session, dos_gerentes: DosGerentes
) -> None:
    equipo = dos_gerentes.uno
    db.add(Limite(gerente_id=equipo.gerente.id, por_pago=10))
    deuda = nueva_deuda(db, equipo.gerente)

    r = cliente.post(iniciar_ruta(deuda.id), headers=cabecera(equipo.asistente))

    assert r.status_code == 200
    cuerpo = r.json()
    assert cuerpo["resultado"] == "requiere_aprobacion"
    assert cuerpo["solicitud_id"] is not None
    assert cuerpo["deuda"]["estado"] == "esperando_aprobacion"


def test_el_gerente_no_inicia_pagos(
    cliente: TestClient, db: Session, dos_gerentes: DosGerentes
) -> None:
    equipo = dos_gerentes.uno
    deuda = nueva_deuda(db, equipo.gerente)

    r = cliente.post(iniciar_ruta(deuda.id), headers=cabecera(equipo.gerente))

    assert (r.status_code, r.json()["code"]) == (403, "SIN_PERMISO")
    db.refresh(deuda)
    assert (deuda.estado, deuda.pago_iniciado_por) == ("pendiente", None)


def test_otro_usuario_recibe_409(
    cliente: TestClient, db: Session, dos_gerentes: DosGerentes
) -> None:
    equipo = dos_gerentes.uno
    deuda = en_proceso_por(
        db, nueva_deuda(db, equipo.gerente), asistente_anterior(db, equipo.gerente)
    )

    r = cliente.post(iniciar_ruta(deuda.id), headers=cabecera(equipo.asistente))

    assert r.status_code == 409
    assert r.json() == {
        "detail": "Otra persona ya está pagando esta deuda.",
        "code": "PAGO_EN_CURSO",
        "field": None,
    }


def test_sin_sesion_responde_401(
    cliente: TestClient, db: Session, dos_gerentes: DosGerentes
) -> None:
    deuda = nueva_deuda(db, dos_gerentes.uno.gerente)
    r = cliente.post(iniciar_ruta(deuda.id))
    assert (r.status_code, r.json()["code"]) == (401, "NO_AUTENTICADO")


def test_sesion_revocada_responde_401(
    cliente: TestClient, db: Session, dos_gerentes: DosGerentes
) -> None:
    equipo = dos_gerentes.uno
    deuda = nueva_deuda(db, equipo.gerente)
    encabezado = cabecera(equipo.asistente)
    equipo.asistente.token_version += 1
    db.flush()

    r = cliente.post(iniciar_ruta(deuda.id), headers=encabezado)

    assert (r.status_code, r.json()["code"]) == (401, "SESION_REVOCADA")
    assert deuda.estado == "pendiente"


@pytest.mark.parametrize("ruta", [iniciar_ruta, cancelar_ruta])
def test_la_deuda_de_otro_gerente_responde_404(
    cliente: TestClient, db: Session, dos_gerentes: DosGerentes, ruta: Callable[[uuid.UUID], str]
) -> None:
    deuda = nueva_deuda(db, dos_gerentes.uno.gerente)
    r = cliente.post(ruta(deuda.id), headers=cabecera(dos_gerentes.dos.asistente))
    assert r.status_code == 404
    assert r.json() == {
        "detail": "No se encontró el recurso solicitado.",
        "code": "NO_ENCONTRADO",
        "field": None,
    }


def test_id_invalido_responde_422(cliente: TestClient, dos_gerentes: DosGerentes) -> None:
    r = cliente.post(
        "/api/v1/deudas/no-es-un-id/iniciar-pago", headers=cabecera(dos_gerentes.uno.asistente)
    )
    assert (r.status_code, r.json()["code"], r.json()["field"]) == (422, "VALIDACION", "deuda_id")


def test_el_dueno_cancela_sin_cuerpo(
    cliente: TestClient, db: Session, dos_gerentes: DosGerentes
) -> None:
    equipo = dos_gerentes.uno
    deuda = nueva_deuda(db, equipo.gerente)
    cliente.post(iniciar_ruta(deuda.id), headers=cabecera(equipo.asistente))

    r = cliente.post(cancelar_ruta(deuda.id), headers=cabecera(equipo.asistente))

    assert r.status_code == 200
    assert r.json()["estado"] == "pendiente"
    assert r.json()["pago_iniciado_por"] is None


def test_el_gerente_cancela_con_motivo(
    cliente: TestClient, db: Session, dos_gerentes: DosGerentes
) -> None:
    equipo = dos_gerentes.uno
    deuda = nueva_deuda(db, equipo.gerente)
    cliente.post(iniciar_ruta(deuda.id), headers=cabecera(equipo.asistente))

    sin_motivo = cliente.post(
        cancelar_ruta(deuda.id), headers=cabecera(equipo.gerente), json={"motivo": " "}
    )
    assert (sin_motivo.status_code, sin_motivo.json()["field"]) == (422, "motivo")

    r = cliente.post(
        cancelar_ruta(deuda.id), headers=cabecera(equipo.gerente), json={"motivo": "Abandonada"}
    )
    assert (r.status_code, r.json()["estado"]) == (200, "pendiente")


def test_motivo_demasiado_largo_responde_422(
    cliente: TestClient, db: Session, dos_gerentes: DosGerentes
) -> None:
    equipo = dos_gerentes.uno
    deuda = nueva_deuda(db, equipo.gerente)
    r = cliente.post(
        cancelar_ruta(deuda.id), headers=cabecera(equipo.gerente), json={"motivo": "x" * 301}
    )
    assert (r.status_code, r.json()["code"], r.json()["field"]) == (422, "VALIDACION", "motivo")


def test_cancelar_sin_intento_responde_409(
    cliente: TestClient, db: Session, dos_gerentes: DosGerentes
) -> None:
    equipo = dos_gerentes.uno
    deuda = nueva_deuda(db, equipo.gerente)
    r = cliente.post(cancelar_ruta(deuda.id), headers=cabecera(equipo.asistente))
    assert (r.status_code, r.json()["code"]) == (409, "SIN_INTENTO")


def test_iniciar_una_deuda_esperando_recibo_responde_409(
    cliente: TestClient, db: Session, dos_gerentes: DosGerentes
) -> None:
    equipo = dos_gerentes.uno
    deuda = nueva_deuda(db, equipo.gerente, monto=None, estado="esperando_recibo")

    r = cliente.post(iniciar_ruta(deuda.id), headers=cabecera(equipo.asistente))

    assert r.status_code == 409
    assert r.json() == {
        "detail": "La deuda aún no tiene monto: espera el recibo del mes.",
        "code": "ESTADO_NO_PERMITIDO",
        "field": None,
    }


def test_el_estado_de_pago_de_una_deuda_sin_monto_expone_null_y_no_cero(
    db: Session, dos_gerentes: DosGerentes
) -> None:
    deuda = nueva_deuda(db, dos_gerentes.uno.gerente, monto=None, estado="esperando_recibo")

    salida = deuda_salida(db, deuda)

    assert (salida.monto, salida.saldo) == (None, None)
    assert salida.model_dump(mode="json")["saldo"] is None
