"""API de registro manual de deudas (H11, TASK-38): CA01 a CA03 y CA09, aislamiento y avisos.

POST /deudas no lleva id en la ruta, así que no está en RUTAS_CON_ID de test_autorizacion_api.py:
el id ajeno llega en el cuerpo y su autorización se prueba aquí con dos gerentes. Las carreras
con transacciones reales están en test_deudas_concurrencia.py.
"""

import uuid
from collections.abc import Iterator
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient
from httpx import Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.eventos import Evento, TipoEvento
from app.core.seguridad import crear_token
from app.core.tiempo import zona_horaria
from app.main import app
from app.models import (
    Auditoria,
    Deuda,
    Notificacion,
    PreferenciaNotificacion,
    Prestamo,
    Servicio,
    Usuario,
)
from app.services import deudas
from app.services.auditoria import Accion
from app.services.notificaciones import TipoNotificacion
from tests.conftest import DosGerentes, nueva_categoria

RUTA = "/api/v1/deudas"
# Hora fija de Lima para las pruebas: martes 20 de octubre de 2026, 10:00.
AHORA = datetime(2026, 10, 20, 10, 0, tzinfo=zona_horaria())
HOY = AHORA.date()

Publicados = list[tuple[uuid.UUID, Evento]]


@pytest.fixture(autouse=True)
def hora_fija(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(deudas, "ahora_lima", lambda: AHORA)


@pytest.fixture
def cliente(db: Session) -> Iterator[TestClient]:
    # Sin with: no arranca el ciclo de vida, que se suscribe a Redis y estas rutas no usan.
    app.dependency_overrides[get_db] = lambda: db
    yield TestClient(app)
    app.dependency_overrides.clear()


def cabecera(usuario: Usuario) -> dict[str, str]:
    return {"Authorization": f"Bearer {crear_token(usuario)}"}


def nuevo_servicio(db: Session, gerente: Usuario, alias: str | None = None) -> Servicio:
    servicio = Servicio(
        gerente_id=gerente.id,
        categoria_id=nueva_categoria(db, gerente).id,
        empresa_nombre="Electro Norte",
        codigo_suministro=uuid.uuid4().hex[:12],
        alias=alias,
    )
    db.add(servicio)
    db.flush()
    return servicio


def datos(servicio: Servicio, **cambios: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "servicio_id": str(servicio.id),
        "monto": "120.50",
        "fecha_vencimiento": "2026-10-25",
    }
    base.update(cambios)
    return {clave: valor for clave, valor in base.items() if valor is not None}


def registrar(cliente: TestClient, usuario: Usuario, cuerpo: dict[str, Any]) -> Response:
    return cliente.post(RUTA, json=cuerpo, headers=cabecera(usuario))


def error(r: Response) -> tuple[int, str, str | None]:
    cuerpo = r.json()
    return r.status_code, cuerpo["code"], cuerpo["field"]


def deudas_de(db: Session, servicio: Servicio) -> list[Deuda]:
    return list(
        db.scalars(select(Deuda).where(Deuda.servicio_id == servicio.id).order_by(Deuda.id))
    )


def eventos_creada(db: Session, gerente: Usuario) -> list[Auditoria]:
    return list(
        db.scalars(
            select(Auditoria).where(
                Auditoria.gerente_id == gerente.id,
                Auditoria.accion == Accion.DEUDA_CREADA.value,
            )
        )
    )


def notificaciones_de(db: Session, usuario: Usuario) -> list[Notificacion]:
    return list(db.scalars(select(Notificacion).where(Notificacion.usuario_id == usuario.id)))


def deuda_existente(
    db: Session, servicio: Servicio, estado: str = "pendiente", monto: str | None = "80.00"
) -> Deuda:
    deuda = Deuda(
        gerente_id=servicio.gerente_id,
        servicio_id=servicio.id,
        periodo=date(2026, 10, 1),
        monto=None if monto is None else Decimal(monto),
        estado=estado,
        fecha_vencimiento=date(2026, 10, 18),
    )
    db.add(deuda)
    db.flush()
    return deuda


# CA01: registro y datos obligatorios


def test_ca01_el_gerente_registra_una_deuda_pendiente(
    cliente: TestClient, db: Session, dos_gerentes: DosGerentes
) -> None:
    gerente = dos_gerentes.uno.gerente
    servicio = nuevo_servicio(db, gerente)

    r = registrar(cliente, gerente, datos(servicio, numero_recibo="  S001-0042  "))

    assert r.status_code == 201, r.text
    cuerpo = r.json()
    assert cuerpo["servicio_id"] == str(servicio.id)
    assert cuerpo["periodo"] == "2026-10"
    assert cuerpo["monto"] == "120.50"
    assert cuerpo["moneda"] == "PEN"
    assert cuerpo["fecha_vencimiento"] == "2026-10-25"
    assert cuerpo["numero_recibo"] == "S001-0042"
    assert (cuerpo["estado"], cuerpo["origen"]) == ("pendiente", "manual")
    assert cuerpo["creado_por"] == str(gerente.id)
    assert cuerpo["advertencias"] == {"vencida": False}
    [deuda] = deudas_de(db, servicio)
    assert str(deuda.id) == cuerpo["id"]
    assert deuda.gerente_id == gerente.id
    assert deuda.periodo == date(2026, 10, 1)
    assert deuda.monto == Decimal("120.50")
    assert (deuda.cuota_numero, deuda.prestamo_id, deuda.recibo_url) == (None, None, None)
    [evento] = eventos_creada(db, gerente)
    assert evento.entidad_id == deuda.id
    assert evento.usuario_id == gerente.id
    assert evento.detalle == {
        "servicio_id": str(servicio.id),
        "periodo": "2026-10",
        "monto": "120.50",
        "moneda": "PEN",
        "fecha_vencimiento": "2026-10-25",
        "numero_recibo": "S001-0042",
        "vencida": False,
    }


def test_ca01_la_asistente_registra_en_un_servicio_de_su_gerente(
    cliente: TestClient, db: Session, dos_gerentes: DosGerentes
) -> None:
    equipo = dos_gerentes.uno
    servicio = nuevo_servicio(db, equipo.gerente)

    r = registrar(cliente, equipo.asistente, datos(servicio))

    assert r.status_code == 201, r.text
    assert r.json()["creado_por"] == str(equipo.asistente.id)
    [deuda] = deudas_de(db, servicio)
    assert deuda.gerente_id == equipo.gerente.id
    [evento] = eventos_creada(db, equipo.gerente)
    assert evento.usuario_id == equipo.asistente.id


@pytest.mark.parametrize("campo", ["servicio_id", "monto", "fecha_vencimiento"])
def test_ca01_servicio_monto_y_vencimiento_son_obligatorios(
    cliente: TestClient, db: Session, dos_gerentes: DosGerentes, campo: str
) -> None:
    gerente = dos_gerentes.uno.gerente
    servicio = nuevo_servicio(db, gerente)
    cuerpo = datos(servicio)
    del cuerpo[campo]

    r = registrar(cliente, gerente, cuerpo)

    assert error(r) == (422, "VALIDACION", campo)
    assert r.json()["detail"] == "Este campo es obligatorio."
    assert deudas_de(db, servicio) == []


@pytest.mark.parametrize(
    "monto", ["0", "0.00", "-5", "10.555", "12345678901.00", "abc", "NaN", "Infinity", None]
)
def test_ca01_el_monto_debe_ser_positivo_con_dos_decimales(
    cliente: TestClient, db: Session, dos_gerentes: DosGerentes, monto: str | None
) -> None:
    gerente = dos_gerentes.uno.gerente
    servicio = nuevo_servicio(db, gerente)
    cuerpo = datos(servicio) | {"monto": monto}

    r = registrar(cliente, gerente, cuerpo)

    assert error(r) == (422, "VALIDACION", "monto")
    assert deudas_de(db, servicio) == []


@pytest.mark.parametrize(("monto", "guardado"), [(35.9, "35.90"), ("9999999999.99", None)])
def test_ca01_acepta_montos_en_numero_o_texto_hasta_el_maximo(
    cliente: TestClient,
    db: Session,
    dos_gerentes: DosGerentes,
    monto: float | str,
    guardado: str | None,
) -> None:
    gerente = dos_gerentes.uno.gerente
    servicio = nuevo_servicio(db, gerente)

    r = registrar(cliente, gerente, datos(servicio, monto=monto))

    assert r.status_code == 201, r.text
    assert r.json()["monto"] == (guardado or str(monto))
    [deuda] = deudas_de(db, servicio)
    assert deuda.monto == Decimal(guardado or str(monto))


@pytest.mark.parametrize("fecha", ["2026-02-30", "25/10/2026", ""])
def test_ca01_el_vencimiento_debe_ser_una_fecha_valida(
    cliente: TestClient, db: Session, dos_gerentes: DosGerentes, fecha: str
) -> None:
    gerente = dos_gerentes.uno.gerente
    servicio = nuevo_servicio(db, gerente)

    r = registrar(cliente, gerente, datos(servicio, fecha_vencimiento=fecha))

    assert error(r) == (422, "VALIDACION", "fecha_vencimiento")


def test_ca01_el_numero_de_recibo_es_opcional_y_tiene_largo_maximo(
    cliente: TestClient, db: Session, dos_gerentes: DosGerentes
) -> None:
    gerente = dos_gerentes.uno.gerente
    vacio = registrar(cliente, gerente, datos(nuevo_servicio(db, gerente), numero_recibo="   "))
    largo = registrar(cliente, gerente, datos(nuevo_servicio(db, gerente), numero_recibo="9" * 61))

    assert vacio.status_code == 201, vacio.text
    assert vacio.json()["numero_recibo"] is None
    assert error(largo) == (422, "VALIDACION", "numero_recibo")


def test_el_cuerpo_no_decide_estado_origen_ni_cuota(
    cliente: TestClient, db: Session, dos_gerentes: DosGerentes
) -> None:
    gerente = dos_gerentes.uno.gerente
    servicio = nuevo_servicio(db, gerente)
    ajenos = {"estado": "pagada", "origen": "robot", "cuota_numero": 3, "recibo_url": "x.pdf"}

    r = registrar(cliente, gerente, datos(servicio) | ajenos)

    assert r.status_code == 201, r.text
    [deuda] = deudas_de(db, servicio)
    assert (deuda.estado, deuda.origen, deuda.cuota_numero) == ("pendiente", "manual", None)
    assert deuda.recibo_url is None


# CA01: periodo


@pytest.mark.parametrize(
    ("vencimiento", "periodo"),
    [
        ("2026-10-25", "2026-10"),
        ("2026-01-31", "2026-01"),
        ("2026-02-28", "2026-02"),
        ("2028-02-29", "2028-02"),
        ("2026-11-30", "2026-11"),
        ("2026-12-31", "2026-12"),
        ("2027-01-01", "2027-01"),
    ],
)
def test_ca01_sin_periodo_se_usa_el_mes_del_vencimiento(
    cliente: TestClient, db: Session, dos_gerentes: DosGerentes, vencimiento: str, periodo: str
) -> None:
    gerente = dos_gerentes.uno.gerente
    servicio = nuevo_servicio(db, gerente)

    r = registrar(cliente, gerente, datos(servicio, fecha_vencimiento=vencimiento))

    assert r.status_code == 201, r.text
    assert r.json()["periodo"] == periodo
    [deuda] = deudas_de(db, servicio)
    assert deuda.periodo == date.fromisoformat(f"{periodo}-01")


def test_ca01_el_periodo_indicado_puede_ser_otro_mes_que_el_vencimiento(
    cliente: TestClient, db: Session, dos_gerentes: DosGerentes
) -> None:
    gerente = dos_gerentes.uno.gerente
    servicio = nuevo_servicio(db, gerente)

    r = registrar(
        cliente, gerente, datos(servicio, periodo="2026-09", fecha_vencimiento="2026-10-05")
    )

    assert r.status_code == 201, r.text
    assert r.json()["periodo"] == "2026-09"
    [deuda] = deudas_de(db, servicio)
    assert deuda.periodo == date(2026, 9, 1)


@pytest.mark.parametrize(
    "periodo", ["2026-13", "2026-00", "2026-1", "2026-10-01", "10-2026", "0999-10", "", 202610]
)
def test_ca01_el_periodo_debe_tener_el_formato_aaaa_mm(
    cliente: TestClient, db: Session, dos_gerentes: DosGerentes, periodo: object
) -> None:
    gerente = dos_gerentes.uno.gerente
    servicio = nuevo_servicio(db, gerente)

    r = registrar(cliente, gerente, datos(servicio, periodo=periodo))

    assert error(r) == (422, "VALIDACION", "periodo")
    assert deudas_de(db, servicio) == []


# CA09: moneda


def test_ca09_la_moneda_puede_ser_soles_o_dolares(
    cliente: TestClient, db: Session, dos_gerentes: DosGerentes
) -> None:
    gerente = dos_gerentes.uno.gerente
    dolares = registrar(cliente, gerente, datos(nuevo_servicio(db, gerente), moneda="USD"))
    soles = registrar(cliente, gerente, datos(nuevo_servicio(db, gerente), moneda="PEN"))
    otra = registrar(cliente, gerente, datos(nuevo_servicio(db, gerente), moneda="EUR"))
    minuscula = registrar(cliente, gerente, datos(nuevo_servicio(db, gerente), moneda="usd"))

    assert (dolares.status_code, dolares.json()["moneda"]) == (201, "USD")
    assert (soles.status_code, soles.json()["moneda"]) == (201, "PEN")
    assert error(otra) == (422, "VALIDACION", "moneda")
    assert error(minuscula) == (422, "VALIDACION", "moneda")


# CA02: deuda vencida


@pytest.mark.parametrize(("dias", "vencida"), [(-30, True), (-1, True), (0, False), (1, False)])
def test_ca02_una_deuda_vencida_se_registra_con_advertencia(
    cliente: TestClient, db: Session, dos_gerentes: DosGerentes, dias: int, vencida: bool
) -> None:
    gerente = dos_gerentes.uno.gerente
    servicio = nuevo_servicio(db, gerente)
    vencimiento = HOY + timedelta(days=dias)

    r = registrar(cliente, gerente, datos(servicio, fecha_vencimiento=vencimiento.isoformat()))

    assert r.status_code == 201, r.text
    assert r.json()["advertencias"] == {"vencida": vencida}
    assert r.json()["estado"] == "pendiente"
    [evento] = eventos_creada(db, gerente)
    assert evento.detalle["vencida"] is vencida


@pytest.mark.parametrize(
    ("hora_lima", "vencida"),
    [
        # 23:30 del 20 en Lima ya es 21 en UTC: la deuda del 20 todavía no está vencida.
        (datetime(2026, 10, 20, 23, 30), False),
        (datetime(2026, 10, 21, 0, 10), True),
    ],
)
def test_ca02_hoy_se_calcula_en_lima(
    cliente: TestClient,
    db: Session,
    dos_gerentes: DosGerentes,
    monkeypatch: pytest.MonkeyPatch,
    hora_lima: datetime,
    vencida: bool,
) -> None:
    ahora = hora_lima.replace(tzinfo=zona_horaria())
    monkeypatch.setattr(deudas, "ahora_lima", lambda: ahora)
    gerente = dos_gerentes.uno.gerente
    servicio = nuevo_servicio(db, gerente)

    r = registrar(cliente, gerente, datos(servicio, fecha_vencimiento="2026-10-20"))

    assert r.status_code == 201, r.text
    assert r.json()["advertencias"] == {"vencida": vencida}


# CA03: duplicado


def test_ca03_el_mismo_servicio_y_periodo_responde_409_con_la_deuda_existente(
    cliente: TestClient, db: Session, dos_gerentes: DosGerentes
) -> None:
    gerente = dos_gerentes.uno.gerente
    servicio = nuevo_servicio(db, gerente)
    primera = registrar(cliente, gerente, datos(servicio, monto="99.90"))
    eventos = len(eventos_creada(db, gerente))

    # Periodo indicado igual al que se derivó del vencimiento de la primera.
    r = registrar(
        cliente, gerente, datos(servicio, periodo="2026-10", fecha_vencimiento="2026-11-02")
    )

    assert error(r) == (409, "DUPLICADO", "periodo")
    assert r.json() == {
        "detail": "Ya existe una deuda de este servicio para ese periodo.",
        "code": "DUPLICADO",
        "field": "periodo",
        "deuda_existente": {
            "id": primera.json()["id"],
            "periodo": "2026-10",
            "estado": "pendiente",
            "monto": "99.90",
            "moneda": "PEN",
            "fecha_vencimiento": "2026-10-25",
        },
    }
    assert [str(d.id) for d in deudas_de(db, servicio)] == [primera.json()["id"]]
    assert len(eventos_creada(db, gerente)) == eventos


@pytest.mark.parametrize(("estado", "monto"), [("esperando_recibo", None), ("pagada", "80.00")])
def test_ca03_cualquier_deuda_no_anulada_ocupa_el_periodo(
    cliente: TestClient, db: Session, dos_gerentes: DosGerentes, estado: str, monto: str | None
) -> None:
    gerente = dos_gerentes.uno.gerente
    servicio = nuevo_servicio(db, gerente)
    existente = deuda_existente(db, servicio, estado, monto)

    r = registrar(cliente, gerente, datos(servicio))

    assert error(r) == (409, "DUPLICADO", "periodo")
    referencia = r.json()["deuda_existente"]
    assert (referencia["id"], referencia["estado"]) == (str(existente.id), estado)
    assert referencia["monto"] == monto


def test_ca03_no_hay_confirmacion_que_salte_la_unicidad(
    cliente: TestClient, db: Session, dos_gerentes: DosGerentes
) -> None:
    gerente = dos_gerentes.uno.gerente
    servicio = nuevo_servicio(db, gerente)
    deuda_existente(db, servicio)

    r = registrar(cliente, gerente, datos(servicio) | {"confirmar": True, "forzar": True})

    assert error(r) == (409, "DUPLICADO", "periodo")
    assert len(deudas_de(db, servicio)) == 1


def test_ca03_otro_periodo_del_mismo_servicio_si_se_registra(
    cliente: TestClient, db: Session, dos_gerentes: DosGerentes
) -> None:
    gerente = dos_gerentes.uno.gerente
    servicio = nuevo_servicio(db, gerente)
    deuda_existente(db, servicio)

    r = registrar(cliente, gerente, datos(servicio, fecha_vencimiento="2026-11-25"))

    assert r.status_code == 201, r.text
    assert r.json()["periodo"] == "2026-11"


def test_ca03_una_deuda_anulada_permite_registrar_otra_del_mismo_periodo(
    cliente: TestClient, db: Session, dos_gerentes: DosGerentes
) -> None:
    gerente = dos_gerentes.uno.gerente
    servicio = nuevo_servicio(db, gerente)
    anulada = deuda_existente(db, servicio, "anulada", None)

    nueva = registrar(cliente, gerente, datos(servicio))
    otra_vez = registrar(cliente, gerente, datos(servicio))

    assert nueva.status_code == 201, nueva.text
    # Con una anulada y una activa, el duplicado apunta a la activa.
    assert error(otra_vez) == (409, "DUPLICADO", "periodo")
    assert otra_vez.json()["deuda_existente"]["id"] == nueva.json()["id"]
    assert {d.id: d.estado for d in deudas_de(db, servicio)} == {
        anulada.id: "anulada",
        uuid.UUID(nueva.json()["id"]): "pendiente",
    }


def test_ca03_una_cuota_de_prestamo_del_periodo_no_choca_con_la_deuda_manual(
    cliente: TestClient, db: Session, dos_gerentes: DosGerentes
) -> None:
    gerente = dos_gerentes.uno.gerente
    servicio = nuevo_servicio(db, gerente)
    prestamo = Prestamo(
        servicio_id=servicio.id,
        monto_total=Decimal("1000.00"),
        cuotas_total=10,
        monto_cuota=Decimal("100.00"),
        fecha_primera_cuota=date(2026, 10, 18),
    )
    db.add(prestamo)
    db.flush()
    cuota = deuda_existente(db, servicio)
    cuota.prestamo_id, cuota.cuota_numero = prestamo.id, 1
    db.flush()

    r = registrar(cliente, gerente, datos(servicio))

    assert r.status_code == 201, r.text
    assert len(deudas_de(db, servicio)) == 2


# Servicio activo y propio


def test_un_servicio_de_baja_no_admite_deudas_nuevas(
    cliente: TestClient, db: Session, dos_gerentes: DosGerentes
) -> None:
    gerente = dos_gerentes.uno.gerente
    servicio = nuevo_servicio(db, gerente)
    servicio.estado = "baja"
    db.flush()

    r = registrar(cliente, gerente, datos(servicio))

    assert error(r) == (409, "SERVICIO_DE_BAJA", "servicio_id")
    assert deudas_de(db, servicio) == []
    assert eventos_creada(db, gerente) == []


def test_un_servicio_eliminado_responde_404(
    cliente: TestClient, db: Session, dos_gerentes: DosGerentes
) -> None:
    gerente = dos_gerentes.uno.gerente
    servicio = nuevo_servicio(db, gerente)
    servicio.eliminado_en = AHORA
    db.flush()

    r = registrar(cliente, gerente, datos(servicio))

    assert error(r) == (404, "NO_ENCONTRADO", "servicio_id")
    assert deudas_de(db, servicio) == []


@pytest.mark.parametrize("actor", ["gerente", "asistente"])
def test_dos_gerentes_el_servicio_ajeno_responde_lo_mismo_que_uno_inexistente(
    cliente: TestClient, db: Session, dos_gerentes: DosGerentes, actor: str
) -> None:
    ajeno = nuevo_servicio(db, dos_gerentes.uno.gerente)
    usuario = getattr(dos_gerentes.dos, actor)
    auditados = db.scalar(select(func.count()).select_from(Auditoria))

    con_ajeno = registrar(cliente, usuario, datos(ajeno))
    con_inexistente = registrar(cliente, usuario, datos(ajeno, servicio_id=str(uuid.uuid4())))

    assert error(con_ajeno) == (404, "NO_ENCONTRADO", "servicio_id")
    assert con_ajeno.json() == con_inexistente.json()
    assert deudas_de(db, ajeno) == []
    assert db.scalar(select(func.count()).select_from(Auditoria)) == auditados


def test_dos_gerentes_registran_el_mismo_periodo_en_sus_servicios(
    cliente: TestClient, db: Session, dos_gerentes: DosGerentes
) -> None:
    uno = nuevo_servicio(db, dos_gerentes.uno.gerente)
    dos = nuevo_servicio(db, dos_gerentes.dos.gerente)

    r_uno = registrar(cliente, dos_gerentes.uno.asistente, datos(uno))
    r_dos = registrar(cliente, dos_gerentes.dos.asistente, datos(dos))

    assert (r_uno.status_code, r_dos.status_code) == (201, 201)
    [deuda_uno], [deuda_dos] = deudas_de(db, uno), deudas_de(db, dos)
    assert deuda_uno.gerente_id == dos_gerentes.uno.gerente.id
    assert deuda_dos.gerente_id == dos_gerentes.dos.gerente.id
    assert len(eventos_creada(db, dos_gerentes.uno.gerente)) == 1
    assert len(eventos_creada(db, dos_gerentes.dos.gerente)) == 1


def test_sin_sesion_responde_401(
    cliente: TestClient, db: Session, dos_gerentes: DosGerentes
) -> None:
    servicio = nuevo_servicio(db, dos_gerentes.uno.gerente)

    r = cliente.post(RUTA, json=datos(servicio))

    assert error(r)[:2] == (401, "NO_AUTENTICADO")
    assert deudas_de(db, servicio) == []


# Aviso al gerente


def test_si_registra_la_asistente_se_avisa_al_gerente_tras_el_commit(
    cliente: TestClient, db: Session, dos_gerentes: DosGerentes, publicados: Publicados
) -> None:
    equipo = dos_gerentes.uno
    servicio = nuevo_servicio(db, equipo.gerente, alias="Luz de la casa")

    r = registrar(cliente, equipo.asistente, datos(servicio))

    assert r.status_code == 201, r.text
    deuda_id = uuid.UUID(r.json()["id"])
    [aviso] = notificaciones_de(db, equipo.gerente)
    assert aviso.tipo == TipoNotificacion.DEUDA_CREADA.value
    assert aviso.deuda_id == deuda_id
    assert aviso.clave_evento == f"deuda_creada:{deuda_id}"
    assert aviso.urgente is False
    assert "Luz de la casa" in aviso.mensaje
    assert "PEN 120.50" in aviso.mensaje
    assert "25/10/2026" in aviso.mensaje
    assert notificaciones_de(db, equipo.asistente) == []
    assert [(destino, e.tipo) for destino, e in publicados] == [
        (equipo.gerente.id, TipoEvento.NOTIFICACION)
    ]


def test_si_registra_el_gerente_no_se_avisa_a_nadie(
    cliente: TestClient, db: Session, dos_gerentes: DosGerentes, publicados: Publicados
) -> None:
    equipo = dos_gerentes.uno
    servicio = nuevo_servicio(db, equipo.gerente)

    r = registrar(cliente, equipo.gerente, datos(servicio))

    assert r.status_code == 201, r.text
    assert notificaciones_de(db, equipo.gerente) == []
    assert notificaciones_de(db, equipo.asistente) == []
    assert publicados == []


def test_el_aviso_respeta_la_preferencia_del_gerente(
    cliente: TestClient, db: Session, dos_gerentes: DosGerentes, publicados: Publicados
) -> None:
    equipo = dos_gerentes.uno
    db.add(
        PreferenciaNotificacion(
            usuario_id=equipo.gerente.id,
            tipo=TipoNotificacion.DEUDA_CREADA.value,
            canal="app",
            activa=False,
        )
    )
    db.flush()
    servicio = nuevo_servicio(db, equipo.gerente)

    r = registrar(cliente, equipo.asistente, datos(servicio))

    assert r.status_code == 201, r.text
    assert notificaciones_de(db, equipo.gerente) == []
    assert publicados == []


def test_un_registro_rechazado_no_avisa(
    cliente: TestClient, db: Session, dos_gerentes: DosGerentes, publicados: Publicados
) -> None:
    equipo = dos_gerentes.uno
    servicio = nuevo_servicio(db, equipo.gerente)
    deuda_existente(db, servicio)

    r = registrar(cliente, equipo.asistente, datos(servicio))

    assert error(r)[:2] == (409, "DUPLICADO")
    assert notificaciones_de(db, equipo.gerente) == []
    assert publicados == []
