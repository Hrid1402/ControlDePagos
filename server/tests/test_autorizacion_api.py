"""Autorización con dos gerentes en las rutas que reciben un id (H01, TASK-5).

Recibir un id no autoriza a usarlo: el gerente o la asistente de otro equipo recibe el mismo 404
que un id inexistente, y el rol equivocado recibe 403 antes de que se busque el recurso, así que
tampoco sabe si existe. Ocultar una opción del menú no reemplaza esta comprobación.

La matriz solo tiene las celdas que no prueban los archivos de cada módulo; RUTAS_CON_ID dice
dónde está el resto. La última prueba compara RUTAS_CON_ID con el esquema OpenAPI: una ruta nueva
con id falla aquí hasta que alguien revise su autorización y la agregue. El esquema no incluye
las rutas de documentación ni las marcadas include_in_schema=False; una ruta con id no debe
ocultarse del esquema.
"""

import uuid
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencias import Origen
from app.core.seguridad import crear_token
from app.main import app
from app.models import Auditoria, Deuda, OrdenPago, Servicio, Usuario
from app.services.pagos import iniciar_pago
from tests.conftest import DosGerentes, nueva_categoria, nueva_deuda, nueva_orden

NO_ENCONTRADO = (404, "NO_ENCONTRADO")
SIN_PERMISO = (403, "SIN_PERMISO")

# Cada ruta con id y dónde se prueban las celdas que no están en MATRIZ.
RUTAS_CON_ID: dict[tuple[str, str], str] = {
    ("GET", "/api/v1/servicios/{servicio_id}"): (
        "asistente ajena: test_api_servicios::test_otro_gerente_no_ve_ni_modifica_el_servicio"
    ),
    ("PUT", "/api/v1/servicios/{servicio_id}"): (
        "asistente ajena: test_api_servicios::test_otro_gerente_no_ve_ni_modifica_el_servicio"
    ),
    ("POST", "/api/v1/servicios/{servicio_id}/baja"): (
        "gerente ajeno: test_api_servicios::test_otro_gerente_no_ve_ni_modifica_el_servicio; "
        "asistente propia: test_api_servicios::test_solo_el_gerente_da_de_baja_y_reactiva"
    ),
    ("POST", "/api/v1/servicios/{servicio_id}/reactivar"): (
        "gerente ajeno: test_api_servicios::test_otro_gerente_no_ve_ni_modifica_el_servicio; "
        "asistente propia: test_api_servicios::test_solo_el_gerente_da_de_baja_y_reactiva"
    ),
    ("POST", "/api/v1/deudas/{deuda_id}/iniciar-pago"): (
        "asistente ajena: test_api_pagos::test_la_deuda_de_otro_gerente_responde_404"
    ),
    ("POST", "/api/v1/deudas/{deuda_id}/cancelar-inicio"): (
        "asistente ajena: test_api_pagos::test_la_deuda_de_otro_gerente_responde_404"
    ),
    ("POST", "/api/v1/deudas/{deuda_id}/fijar"): (
        "asistente ajena: test_api_bandeja::test_dos_gerentes_no_ven_ni_tocan_deudas_ajenas; "
        "gerente propio: test_api_bandeja::test_permisos_y_validacion"
    ),
    ("POST", "/api/v1/deudas/{deuda_id}/recordar-manana"): (
        "asistente ajena: test_api_bandeja::test_dos_gerentes_no_ven_ni_tocan_deudas_ajenas; "
        "gerente propio: test_api_bandeja::test_permisos_y_validacion"
    ),
    ("POST", "/api/v1/ordenes/{orden_id}/vista"): (
        "asistente ajena: test_api_ordenes::test_dos_gerentes_no_ven_ni_responden_ordenes_ajenas"
    ),
    ("POST", "/api/v1/ordenes/{orden_id}/aceptar"): (
        "asistente ajena: test_api_ordenes::test_dos_gerentes_no_ven_ni_responden_ordenes_ajenas"
    ),
    ("POST", "/api/v1/ordenes/{orden_id}/rechazar"): (
        "asistente ajena: test_api_ordenes::test_dos_gerentes_no_ven_ni_responden_ordenes_ajenas"
    ),
}


@dataclass(frozen=True)
class Recursos:
    """Recursos del equipo uno. Las solicitudes las hacen el equipo dos o el rol equivocado."""

    servicio: Servicio
    deuda: Deuda
    en_proceso: Deuda
    orden: OrdenPago


@dataclass(frozen=True)
class Caso:
    metodo: str
    ruta: str
    actor: str  # "gerente_ajeno", "asistente_ajena" o "gerente_propio"
    esperado: tuple[int, str]
    recurso: Callable[[Recursos], Servicio | Deuda | OrdenPago]
    # Un cuerpo válido para quien llama: así el rechazo solo puede venir de la autorización.
    cuerpo: Callable[[Session, DosGerentes], dict[str, Any] | None] = lambda db, equipos: None

    def __str__(self) -> str:
        return f"{self.metodo} {self.ruta} {self.actor}"


def servicio_del_otro_equipo(db: Session, equipos: DosGerentes) -> dict[str, Any]:
    return {
        "categoria_id": str(nueva_categoria(db, equipos.dos.gerente).id),
        "empresa_nombre": "Electro Norte",
        "codigo_suministro": uuid.uuid4().hex[:12],
        "lugar_pago": "agente_bcp",
    }


def sin_cuerpo(db: Session, equipos: DosGerentes) -> None:
    return None


def motivo_de_cancelacion(db: Session, equipos: DosGerentes) -> dict[str, Any]:
    return {"motivo": "Intento ajeno"}


def motivo_de_rechazo(db: Session, equipos: DosGerentes) -> dict[str, Any]:
    return {"motivo": "otro_medio"}


def servicio(r: Recursos) -> Servicio:
    return r.servicio


def deuda(r: Recursos) -> Deuda:
    return r.deuda


def en_proceso(r: Recursos) -> Deuda:
    return r.en_proceso


def orden(r: Recursos) -> OrdenPago:
    return r.orden


ORDENES = ("vista", "aceptar", "rechazar")

MATRIZ = [
    Caso("GET", "/api/v1/servicios/{servicio_id}", "gerente_ajeno", NO_ENCONTRADO, servicio),
    Caso(
        "PUT",
        "/api/v1/servicios/{servicio_id}",
        "gerente_ajeno",
        NO_ENCONTRADO,
        servicio,
        servicio_del_otro_equipo,
    ),
    Caso("POST", "/api/v1/servicios/{servicio_id}/baja", "asistente_ajena", SIN_PERMISO, servicio),
    Caso(
        "POST",
        "/api/v1/servicios/{servicio_id}/reactivar",
        "asistente_ajena",
        SIN_PERMISO,
        servicio,
    ),
    Caso("POST", "/api/v1/deudas/{deuda_id}/iniciar-pago", "gerente_ajeno", NO_ENCONTRADO, deuda),
    Caso(
        "POST",
        "/api/v1/deudas/{deuda_id}/cancelar-inicio",
        "gerente_ajeno",
        NO_ENCONTRADO,
        en_proceso,
        motivo_de_cancelacion,
    ),
    Caso("POST", "/api/v1/deudas/{deuda_id}/fijar", "gerente_ajeno", SIN_PERMISO, deuda),
    Caso("POST", "/api/v1/deudas/{deuda_id}/recordar-manana", "gerente_ajeno", SIN_PERMISO, deuda),
    *(
        Caso(
            "POST",
            f"/api/v1/ordenes/{{orden_id}}/{accion}",
            actor,
            SIN_PERMISO,
            orden,
            motivo_de_rechazo if accion == "rechazar" else sin_cuerpo,
        )
        for accion in ORDENES
        for actor in ("gerente_propio", "gerente_ajeno")
    ),
]


@pytest.fixture
def cliente(db: Session) -> Iterator[TestClient]:
    # Sin with: no arranca el ciclo de vida, que se suscribe a Redis y estas rutas no usan.
    app.dependency_overrides[get_db] = lambda: db
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def recursos(db: Session, dos_gerentes: DosGerentes) -> Recursos:
    uno = dos_gerentes.uno
    pendiente = nueva_deuda(db, uno.gerente)
    iniciada = nueva_deuda(db, uno.gerente)
    iniciar_pago(db, uno.asistente, iniciada.id, origen=Origen(dispositivo=None, ip=None))
    db.flush()
    return Recursos(
        servicio=db.get_one(Servicio, pendiente.servicio_id),
        deuda=pendiente,
        en_proceso=iniciada,
        orden=nueva_orden(db, nueva_deuda(db, uno.gerente), asistente=uno.asistente),
    )


def actor(equipos: DosGerentes, nombre: str) -> Usuario:
    return {
        "gerente_ajeno": equipos.dos.gerente,
        "asistente_ajena": equipos.dos.asistente,
        "gerente_propio": equipos.uno.gerente,
    }[nombre]


def columnas(objeto: Servicio | Deuda | OrdenPago) -> dict[str, Any]:
    return {c.key: getattr(objeto, c.key) for c in objeto.__mapper__.column_attrs}


@pytest.mark.parametrize("caso", MATRIZ, ids=str)
def test_otro_equipo_o_rol_equivocado_no_accede_por_id(
    cliente: TestClient,
    db: Session,
    dos_gerentes: DosGerentes,
    recursos: Recursos,
    caso: Caso,
) -> None:
    objetivo = caso.recurso(recursos)
    antes = columnas(objetivo)
    eventos = db.scalar(select(func.count()).select_from(Auditoria))
    nombre_id = caso.ruta.split("{")[1].split("}")[0]
    usuario = actor(dos_gerentes, caso.actor)

    r = cliente.request(
        caso.metodo,
        caso.ruta.format(**{nombre_id: objetivo.id}),
        json=caso.cuerpo(db, dos_gerentes),
        headers={"Authorization": f"Bearer {crear_token(usuario)}"},
    )

    assert (r.status_code, r.json()["code"]) == caso.esperado, r.text
    db.refresh(objetivo)
    assert columnas(objetivo) == antes
    assert db.scalar(select(func.count()).select_from(Auditoria)) == eventos


@pytest.mark.parametrize("caso", [c for c in MATRIZ if c.esperado == NO_ENCONTRADO], ids=str)
def test_el_404_ajeno_es_igual_al_de_un_id_inexistente(
    cliente: TestClient,
    db: Session,
    dos_gerentes: DosGerentes,
    recursos: Recursos,
    caso: Caso,
) -> None:
    nombre_id = caso.ruta.split("{")[1].split("}")[0]
    cabecera = {"Authorization": f"Bearer {crear_token(actor(dos_gerentes, caso.actor))}"}

    def pedir(recurso_id: uuid.UUID) -> Any:
        ruta = caso.ruta.format(**{nombre_id: recurso_id})
        return cliente.request(
            caso.metodo, ruta, json=caso.cuerpo(db, dos_gerentes), headers=cabecera
        )

    ajeno, inexistente = pedir(caso.recurso(recursos).id), pedir(uuid.uuid4())

    assert (ajeno.status_code, ajeno.json()) == (inexistente.status_code, inexistente.json())


def test_cada_ruta_con_id_tiene_su_autorizacion_revisada() -> None:
    publicadas = {
        (metodo.upper(), ruta)
        for ruta, operaciones in app.openapi()["paths"].items()
        if "{" in ruta
        for metodo in operaciones
    }

    assert publicadas == set(RUTAS_CON_ID)
    assert {(c.metodo, c.ruta) for c in MATRIZ} <= publicadas
