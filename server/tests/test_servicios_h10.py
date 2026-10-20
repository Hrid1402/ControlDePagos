"""H10 de punta a punta (TASK-35): recorridos completos por la API que cruzan registro, edición,
baja, pagos e historial. Los casos sueltos de cada regla están en test_api_servicios.py y
test_servicios_esquema.py; aquí se prueba que encajan entre sí.
"""

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.dependencias import Origen
from app.models import Deuda, Empresa, Servicio
from app.services.pagos import ResultadoInicio, iniciar_pago
from tests.conftest import DosGerentes, nueva_categoria
from tests.test_api_servicios import (
    ENEL,
    RUTA,
    SEDAPAL,
    cabecera,
    cliente,
    creado,
    crear,
    datos,
    error,
)

__all__ = ["cliente"]

ORIGEN = Origen(dispositivo="pruebas", ip=None)
AHORA = datetime(2026, 10, 19, 17, 0, tzinfo=UTC)


def deuda(
    db: Session, servicio: dict[str, Any], gerente_id: uuid.UUID, mes: int, estado: str
) -> Deuda:
    nueva = Deuda(
        gerente_id=gerente_id,
        servicio_id=uuid.UUID(servicio["id"]),
        periodo=date(2026, mes, 1),
        monto=None if estado == "esperando_recibo" else Decimal("75.00"),
        estado=estado,
        fecha_vencimiento=date(2026, mes, 25),
    )
    db.add(nueva)
    db.flush()
    return nueva


def test_ca01_ca03_alternar_entre_catalogo_y_nombre_manual_no_esquiva_el_duplicado(
    cliente: TestClient, db: Session, dos_gerentes: DosGerentes
) -> None:
    gerente = dos_gerentes.uno.gerente
    categoria = nueva_categoria(db, gerente)
    escrito = creado(
        cliente, gerente, datos(categoria, empresa_nombre="  enel ", codigo_suministro="12 34")
    )
    manual = creado(
        cliente,
        gerente,
        datos(categoria, empresa_nombre="Electro Oriente", codigo_suministro="AB1"),
    )

    del_catalogo = crear(
        cliente,
        gerente,
        datos(categoria, empresa_nombre=None, empresa_id=str(ENEL.id), codigo_suministro="1234"),
    )
    hacia_manual = cliente.put(
        f"{RUTA}/{escrito['id']}",
        json=datos(categoria, empresa_nombre="electro  oriente", codigo_suministro="ab 1"),
        headers=cabecera(gerente),
    )

    assert (escrito["empresa_id"], escrito["empresa_manual"]) == (str(ENEL.id), False)
    assert manual["empresa_manual"] is True
    assert error(del_catalogo) == (409, "DUPLICADO", "codigo_suministro")
    assert error(hacia_manual) == (409, "DUPLICADO", "codigo_suministro")
    guardado = db.get_one(Servicio, uuid.UUID(escrito["id"]))
    assert (guardado.empresa_id, guardado.codigo_suministro) == (ENEL.id, "1234")


def test_ca02_el_formato_de_la_empresa_tambien_se_valida_al_editar(
    cliente: TestClient, db: Session, dos_gerentes: DosGerentes
) -> None:
    gerente = dos_gerentes.uno.gerente
    db.get_one(Empresa, SEDAPAL.id).patron_codigo = "[0-9]{7}"
    db.flush()
    categoria = nueva_categoria(db, gerente)
    sedapal = {"empresa_nombre": None, "empresa_id": str(SEDAPAL.id)}
    servicio = creado(cliente, gerente, datos(categoria, codigo_suministro="1234567", **sedapal))

    r = cliente.put(
        f"{RUTA}/{servicio['id']}",
        json=datos(categoria, codigo_suministro="12-34", **sedapal),
        headers=cabecera(gerente),
    )

    assert error(r) == (422, "VALIDACION", "codigo_suministro")
    assert db.get_one(Servicio, uuid.UUID(servicio["id"])).codigo_suministro == "1234567"


def test_ca04_a_ca06_lista_y_detalle_muestran_lo_registrado_y_se_puede_vaciar(
    cliente: TestClient, db: Session, dos_gerentes: DosGerentes
) -> None:
    gerente = dos_gerentes.uno.gerente
    categoria = nueva_categoria(db, gerente)
    cuerpo = datos(
        categoria,
        titular="Rosa Díaz",
        alias="Luz oficina",
        lugar_pago="banca_movil",
        notas="Pagar con Yape al 999 888 777.",
    )
    servicio = creado(cliente, gerente, cuerpo)

    [item] = cliente.get(RUTA, headers=cabecera(gerente)).json()["items"]
    detalle = cliente.get(f"{RUTA}/{servicio['id']}", headers=cabecera(gerente)).json()
    campos = ("titular", "alias", "lugar_pago", "notas")
    assert [item[c] for c in campos] == [detalle[c] for c in campos] == [cuerpo[c] for c in campos]

    vaciado = cliente.put(
        f"{RUTA}/{servicio['id']}",
        json=cuerpo | {"titular": "", "alias": " ", "notas": ""},
        headers=cabecera(gerente),
    ).json()
    assert (vaciado["titular"], vaciado["alias"], vaciado["notas"]) == (None, None, None)


def test_ca07_la_advertencia_cuenta_solo_las_deudas_sin_pagar_ni_anular(
    cliente: TestClient, db: Session, dos_gerentes: DosGerentes
) -> None:
    gerente = dos_gerentes.uno.gerente
    categoria = nueva_categoria(db, gerente)
    servicio = creado(cliente, gerente, datos(categoria, codigo_suministro="VIEJO-1"))
    deudas = [
        deuda(db, servicio, gerente.id, mes, estado)
        for mes, estado in enumerate(("pendiente", "esperando_recibo", "pagada", "anulada"), 6)
    ]

    detalle = cliente.get(f"{RUTA}/{servicio['id']}", headers=cabecera(gerente)).json()
    editado = cliente.put(
        f"{RUTA}/{servicio['id']}",
        json=datos(categoria, codigo_suministro="NUEVO-1"),
        headers=cabecera(gerente),
    ).json()

    assert detalle["deudas_pendientes"] == 2
    assert editado["advertencias"] == {"codigo_cambiado": True, "deudas_pendientes": 2}
    for d in deudas:
        db.refresh(d)
    assert {d.servicio_id for d in deudas} == {uuid.UUID(servicio["id"])}
    assert [d.estado for d in deudas] == ["pendiente", "esperando_recibo", "pagada", "anulada"]


def test_ca08_las_deudas_pendientes_de_un_servicio_de_baja_se_siguen_pagando(
    cliente: TestClient, db: Session, dos_gerentes: DosGerentes
) -> None:
    equipo = dos_gerentes.uno
    servicio = creado(cliente, equipo.gerente, datos(nueva_categoria(db, equipo.gerente)))
    pendiente = deuda(db, servicio, equipo.gerente.id, 10, "pendiente")

    baja = cliente.post(f"{RUTA}/{servicio['id']}/baja", headers=cabecera(equipo.gerente))
    inicio = iniciar_pago(db, equipo.asistente, pendiente.id, origen=ORIGEN, ahora=AHORA)

    assert (baja.status_code, baja.json()["deudas_pendientes"]) == (200, 1)
    assert inicio.resultado == ResultadoInicio.INICIADO
    assert pendiente.estado == "en_proceso"


def test_ca09_la_asistente_registra_y_edita_en_cualquier_categoria_pero_no_da_de_baja(
    cliente: TestClient, db: Session, dos_gerentes: DosGerentes
) -> None:
    equipo = dos_gerentes.uno
    asistente = cabecera(equipo.asistente)
    registrados = [
        creado(cliente, equipo.asistente, datos(nueva_categoria(db, equipo.gerente, tipo)))
        for tipo in ("servicio_variable", "monto_fijo", "tarjeta", "prestamo")
    ]
    primero = registrados[0]

    editado = cliente.put(
        f"{RUTA}/{primero['id']}",
        json=datos(nueva_categoria(db, equipo.gerente, "tarjeta"), alias="Visa"),
        headers=asistente,
    )
    baja = cliente.post(f"{RUTA}/{primero['id']}/baja", headers=asistente)

    assert {r["creado_por"] for r in registrados} == {str(equipo.asistente.id)}
    assert (editado.status_code, editado.json()["alias"]) == (200, "Visa")
    assert error(baja)[:2] == (403, "SIN_PERMISO")
    assert db.get_one(Servicio, uuid.UUID(primero["id"])).estado == "activo"


def test_el_ciclo_completo_queda_en_el_historial_del_gerente(
    cliente: TestClient, db: Session, dos_gerentes: DosGerentes
) -> None:
    equipo = dos_gerentes.uno
    categoria = nueva_categoria(db, equipo.gerente)
    servicio = creado(cliente, equipo.asistente, datos(categoria, codigo_suministro="C-1"))
    ruta = f"{RUTA}/{servicio['id']}"
    cliente.put(
        ruta, json=datos(categoria, codigo_suministro="C-2"), headers=cabecera(equipo.asistente)
    )
    cliente.post(f"{ruta}/baja", headers=cabecera(equipo.gerente))
    cliente.post(f"{ruta}/reactivar", headers=cabecera(equipo.gerente))

    historial = cliente.get(
        "/api/v1/auditoria", params={"size": 50}, headers=cabecera(equipo.gerente)
    ).json()["items"]
    propios = [r for r in reversed(historial) if r["entidad_id"] == servicio["id"]]

    assert [(r["accion"], r["usuario_id"]) for r in propios] == [
        ("servicio_creado", str(equipo.asistente.id)),
        ("servicio_actualizado", str(equipo.asistente.id)),
        ("servicio_dado_de_baja", str(equipo.gerente.id)),
        ("servicio_reactivado", str(equipo.gerente.id)),
    ]
    assert propios[2]["detalle"] == {"recurrencias_desactivadas": 0, "deudas_pendientes": 0}
    otro = cliente.get("/api/v1/auditoria", headers=cabecera(dos_gerentes.dos.gerente)).json()
    assert servicio["id"] not in {r["entidad_id"] for r in otro["items"]}
    assert db.scalar(select(Servicio.estado).where(Servicio.id == uuid.UUID(servicio["id"]))) == (
        "activo"
    )
