"""API de listado de deudas (H36, TASK-45): CA01 a CA05 y CA08, aislamiento y errores.

GET /deudas no lleva id en la ruta, así que no está en RUTAS_CON_ID de test_autorizacion_api.py:
los ids ajenos llegan como filtros (categoria y servicio) y su autorización se prueba aquí con
dos gerentes.
"""

import uuid
from collections.abc import Iterator
from datetime import date, datetime
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.seguridad import crear_token
from app.core.tiempo import zona_horaria
from app.main import app
from app.models import Categoria, Deuda, Empresa, Servicio, Usuario
from app.services import deudas
from tests.conftest import DosGerentes, nueva_categoria, nuevo_comprobante

RUTA = "/api/v1/deudas"
# Hora fija de Lima para las pruebas: martes 20 de octubre de 2026, 10:00.
AHORA = datetime(2026, 10, 20, 10, 0, tzinfo=zona_horaria())
CEROS = {
    "cantidad": 0,
    "monto": "0.00",
    "pagado": "0.00",
    "saldo": "0.00",
    "sin_monto": 0,
    "proyectado": "0.00",
    "sin_estimacion": 0,
}


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


def nuevo_servicio(
    db: Session,
    gerente: Usuario,
    *,
    categoria: Categoria | None = None,
    empresa: Empresa | None = None,
    empresa_nombre: str = "Hidrandina",
    codigo: str | None = None,
    alias: str | None = None,
) -> Servicio:
    servicio = Servicio(
        gerente_id=gerente.id,
        categoria_id=(categoria or nueva_categoria(db, gerente)).id,
        empresa_id=empresa.id if empresa else None,
        empresa_nombre=None if empresa else empresa_nombre,
        codigo_suministro=codigo or uuid.uuid4().hex[:12].upper(),
        alias=alias,
    )
    db.add(servicio)
    db.flush()
    return servicio


def nueva(
    db: Session,
    gerente: Usuario,
    monto: str | None = "100.00",
    *,
    moneda: str = "PEN",
    estado: str = "pendiente",
    vence: date = date(2026, 10, 25),
    periodo: date | None = None,
    servicio: Servicio | None = None,
    recibo: str | None = None,
) -> Deuda:
    """Deuda con su propio servicio si no se indica, para no chocar con uq_deuda_periodo."""
    deuda = Deuda(
        gerente_id=gerente.id,
        servicio_id=(servicio or nuevo_servicio(db, gerente)).id,
        periodo=periodo or vence.replace(day=1),
        monto=None if monto is None else Decimal(monto),
        moneda=moneda,
        estado=estado,
        fecha_vencimiento=vence,
        numero_recibo=recibo,
    )
    db.add(deuda)
    db.flush()
    return deuda


def listar(cliente: TestClient, usuario: Usuario, **params: Any) -> dict[str, Any]:
    respuesta = cliente.get(RUTA, params=params, headers=cabecera(usuario))
    assert respuesta.status_code == 200, respuesta.text
    cuerpo: dict[str, Any] = respuesta.json()
    return cuerpo


def ids(cuerpo: dict[str, Any]) -> list[str]:
    return [item["id"] for item in cuerpo["items"]]


def test_cada_gerente_y_su_asistente_ven_solo_sus_deudas(
    cliente: TestClient, db: Session, dos_gerentes: DosGerentes
) -> None:
    uno, dos = dos_gerentes.uno, dos_gerentes.dos
    propias = {str(nueva(db, uno.gerente).id), str(nueva(db, uno.gerente, "50.00").id)}
    ajena = nueva(db, dos.gerente, "999.00")

    for usuario in (uno.gerente, uno.asistente):
        cuerpo = listar(cliente, usuario)
        assert set(ids(cuerpo)) == propias
        assert cuerpo["total"] == 2
        assert cuerpo["totales"]["PEN"]["monto"] == "150.00"
    assert ids(listar(cliente, dos.asistente)) == [str(ajena.id)]


def test_columnas_del_item(cliente: TestClient, db: Session, dos_gerentes: DosGerentes) -> None:
    """CA01: empresa, alias, categoría, periodo, monto, vencimiento y estado, más lo calculado."""
    gerente = dos_gerentes.uno.gerente
    categoria = nueva_categoria(db, gerente, "monto_fijo")
    servicio = nuevo_servicio(db, gerente, categoria=categoria, alias="Casa", codigo="SUM-1")
    deuda = nueva(db, gerente, "80.00", servicio=servicio, recibo="F001-9")

    [item] = listar(cliente, gerente)["items"]

    assert item == {
        "id": str(deuda.id),
        "servicio_id": str(servicio.id),
        "empresa": "Hidrandina",
        "alias": "Casa",
        "codigo_suministro": "SUM-1",
        "categoria": {
            "id": str(categoria.id),
            "nombre": categoria.nombre,
            "color": categoria.color,
            "icono": categoria.icono,
            "tipo": "monto_fijo",
        },
        "periodo": "2026-10",
        "monto": "80.00",
        "moneda": "PEN",
        "pagado": "0.00",
        "saldo": "80.00",
        "monto_proyectado": None,
        "fecha_vencimiento": "2026-10-25",
        "vencida": False,
        "estado": "pendiente",
        "numero_recibo": "F001-9",
    }


def test_categoria_o_servicio_ajeno_responde_como_inexistente(
    cliente: TestClient, db: Session, dos_gerentes: DosGerentes
) -> None:
    asistente = dos_gerentes.uno.asistente
    ajeno = nueva(db, dos_gerentes.dos.gerente)
    servicio_ajeno = db.get_one(Servicio, ajeno.servicio_id)
    casos = {"categoria": servicio_ajeno.categoria_id, "servicio": servicio_ajeno.id}

    for parametro, ajeno_id in casos.items():
        respuestas = [
            cliente.get(RUTA, params={parametro: str(valor)}, headers=cabecera(asistente))
            for valor in (ajeno_id, uuid.uuid4())
        ]
        assert [r.status_code for r in respuestas] == [404, 404]
        assert respuestas[0].json() == respuestas[1].json()
        assert respuestas[0].json()["field"] == parametro


def test_sin_sesion_responde_401(cliente: TestClient) -> None:
    respuesta = cliente.get(RUTA)
    assert respuesta.status_code == 401
    assert respuesta.json()["code"] == "NO_AUTENTICADO"


def test_totales_separados_por_moneda_con_abonos_validados(
    cliente: TestClient, db: Session, dos_gerentes: DosGerentes
) -> None:
    gerente, asistente = dos_gerentes.uno.gerente, dos_gerentes.uno.asistente
    nueva(db, gerente, "100.00")
    parcial = nueva(db, gerente, "200.00", estado="pagada_parcial")
    nuevo_comprobante(db, parcial, asistente, "50.00")
    # Un comprobante en revisión todavía no es abono: no resta.
    nuevo_comprobante(db, parcial, asistente, "30.00", estado="en_revision")
    nueva(db, gerente, "40.00", moneda="USD")

    cuerpo = listar(cliente, gerente)

    assert cuerpo["totales"] == {
        "PEN": CEROS | {"cantidad": 2, "monto": "300.00", "pagado": "50.00", "saldo": "250.00"},
        "USD": CEROS | {"cantidad": 1, "monto": "40.00", "saldo": "40.00"},
    }
    item = next(i for i in cuerpo["items"] if i["id"] == str(parcial.id))
    assert (item["pagado"], item["saldo"]) == ("50.00", "150.00")


def test_filtro_sin_resultados_trae_ambas_monedas_en_cero(
    cliente: TestClient, db: Session, dos_gerentes: DosGerentes
) -> None:
    gerente = dos_gerentes.uno.gerente
    nueva(db, gerente)

    cuerpo = listar(cliente, gerente, q="no existe")

    assert cuerpo == {"items": [], "total": 0, "page": 1, "totales": {"PEN": CEROS, "USD": CEROS}}


def test_totales_de_todo_el_filtro_en_cada_pagina(
    cliente: TestClient, db: Session, dos_gerentes: DosGerentes
) -> None:
    """CA05 y CA08: páginas de 20 y el mismo total del filtro en todas, no solo de la página."""
    gerente = dos_gerentes.uno.gerente
    for i in range(45):
        nueva(db, gerente, f"{i + 1}.00")
    esperado = CEROS | {"cantidad": 45, "monto": "1035.00", "saldo": "1035.00"}

    paginas = [listar(cliente, gerente, page=page) for page in (1, 2, 3)]

    assert [len(p["items"]) for p in paginas] == [20, 20, 5]
    assert all(p["total"] == 45 and p["totales"]["PEN"] == esperado for p in paginas)
    suma = sum(Decimal(i["monto"]) for p in paginas for i in p["items"])
    assert suma == Decimal(esperado["monto"])


def test_deuda_sin_monto_se_proyecta_aparte(
    cliente: TestClient, db: Session, dos_gerentes: DosGerentes
) -> None:
    """Sin recibo no suma como cero: va a sin_monto y su estimación es el mes anterior (H14)."""
    gerente = dos_gerentes.uno.gerente
    con_referencia = nuevo_servicio(db, gerente)
    nueva(db, gerente, "80.00", estado="pagada", vence=date(2026, 9, 25), servicio=con_referencia)
    proyectada = nueva(db, gerente, None, estado="esperando_recibo", servicio=con_referencia)
    # La deuda anterior está anulada: no sirve de referencia.
    anulada_antes = nuevo_servicio(db, gerente)
    nueva(db, gerente, "70.00", estado="anulada", vence=date(2026, 9, 25), servicio=anulada_antes)
    sin_referencia = nueva(db, gerente, None, estado="esperando_recibo", servicio=anulada_antes)
    nueva(db, gerente, "100.00")

    cuerpo = listar(cliente, gerente, mes="2026-10")

    assert cuerpo["totales"]["PEN"] == CEROS | {
        "cantidad": 3,
        "monto": "100.00",
        "saldo": "100.00",
        "sin_monto": 2,
        "proyectado": "80.00",
        "sin_estimacion": 1,
    }
    items = {i["id"]: i for i in cuerpo["items"]}
    assert {k: items[str(proyectada.id)][k] for k in ("monto", "saldo", "monto_proyectado")} == {
        "monto": None,
        "saldo": None,
        "monto_proyectado": "80.00",
    }
    assert items[str(sin_referencia.id)]["monto_proyectado"] is None


@pytest.mark.parametrize(
    ("ahora", "vencida"),
    [
        # 23:30 en Lima ya es el 21 en UTC: todavía no venció.
        (datetime(2026, 10, 20, 23, 30, tzinfo=zona_horaria()), False),
        (datetime(2026, 10, 21, 0, 0, tzinfo=zona_horaria()), True),
    ],
    ids=["antes_de_medianoche", "medianoche"],
)
def test_vencida_cambia_a_la_medianoche_de_lima(
    cliente: TestClient,
    db: Session,
    dos_gerentes: DosGerentes,
    monkeypatch: pytest.MonkeyPatch,
    ahora: datetime,
    vencida: bool,
) -> None:
    monkeypatch.setattr(deudas, "ahora_lima", lambda: ahora)
    gerente = dos_gerentes.uno.gerente
    deuda = nueva(db, gerente, vence=date(2026, 10, 20))
    nueva(db, gerente, estado="pagada", vence=date(2026, 10, 1))
    nueva(db, gerente, estado="anulada", vence=date(2026, 10, 1))

    cuerpo = listar(cliente, gerente, estado=["pendiente", "pagada", "anulada"])
    filtradas = listar(cliente, gerente, vencida="true")

    assert {i["estado"]: i["vencida"] for i in cuerpo["items"]} == {
        "pendiente": vencida,
        "pagada": False,
        "anulada": False,
    }
    assert ids(filtradas) == ([str(deuda.id)] if vencida else [])


def test_vencida_incluye_estados_que_aun_se_cobran(
    cliente: TestClient, db: Session, dos_gerentes: DosGerentes
) -> None:
    gerente = dos_gerentes.uno.gerente
    ayer = date(2026, 10, 19)
    vencidas = {
        str(nueva(db, gerente, "10.00", estado=estado, vence=ayer).id)
        for estado in ("pagada_parcial", "con_problema", "en_proceso")
    }
    vencidas.add(str(nueva(db, gerente, None, estado="esperando_recibo", vence=ayer).id))
    nueva(db, gerente, estado="pagada", vence=ayer)

    assert set(ids(listar(cliente, gerente, vencida="true"))) == vencidas
    assert listar(cliente, gerente, vencida="false")["total"] == 1


ORDENES = ["vencimiento", "-vencimiento", "monto", "-monto", "estado", "-estado"]


@pytest.mark.parametrize("orden", ORDENES)
def test_orden_estable_sin_repetidos_ni_omitidos(
    cliente: TestClient, db: Session, dos_gerentes: DosGerentes, orden: str
) -> None:
    """Muchos empates de vencimiento, monto y estado: el id desempata y las páginas no se pisan."""
    gerente = dos_gerentes.uno.gerente
    creadas = set()
    for i in range(23):
        monto = None if i % 5 == 0 else "10.00"
        estado = "esperando_recibo" if monto is None else ("pendiente", "pagada")[i % 2]
        creadas.add(str(nueva(db, gerente, monto, estado=estado, vence=date(2026, 10, 25)).id))

    vistas = [
        deuda_id
        for page in (1, 2, 3, 4)
        for deuda_id in ids(listar(cliente, gerente, orden=orden, size=7, page=page))
    ]

    assert len(vistas) == len(set(vistas)) == 23
    assert set(vistas) == creadas


def test_orden_por_vencimiento_monto_y_estado(
    cliente: TestClient, db: Session, dos_gerentes: DosGerentes
) -> None:
    """CA04. Sin monto va al final en ambos sentidos; el estado sigue su ciclo de vida."""
    gerente = dos_gerentes.uno.gerente
    sin_monto = nueva(db, gerente, None, estado="esperando_recibo", vence=date(2026, 10, 30))
    pagada = nueva(db, gerente, "5.00", estado="pagada", vence=date(2026, 10, 10))
    pendiente = nueva(db, gerente, "50.00", vence=date(2026, 10, 20))
    a, b, c = str(sin_monto.id), str(pagada.id), str(pendiente.id)

    assert ids(listar(cliente, gerente)) == [b, c, a]
    assert ids(listar(cliente, gerente, orden="-vencimiento")) == [a, c, b]
    assert ids(listar(cliente, gerente, orden="monto")) == [b, c, a]
    assert ids(listar(cliente, gerente, orden="-monto")) == [c, b, a]
    assert ids(listar(cliente, gerente, orden="estado")) == [a, c, b]
    assert ids(listar(cliente, gerente, orden="-estado")) == [b, c, a]


def test_busqueda_por_empresa_alias_codigo_y_recibo(
    cliente: TestClient, db: Session, dos_gerentes: DosGerentes
) -> None:
    """CA02, más el número de recibo. El código se busca también normalizado."""
    gerente = dos_gerentes.uno.gerente
    empresa = Empresa(nombre="Luz del Sur", tipo_servicio="luz")
    db.add(empresa)
    db.flush()
    catalogo = nueva(db, gerente, servicio=nuevo_servicio(db, gerente, empresa=empresa))
    manual = nueva(db, gerente, servicio=nuevo_servicio(db, gerente, empresa_nombre="Sedapal"))
    alias = nueva(db, gerente, servicio=nuevo_servicio(db, gerente, alias="Casa de playa"))
    codigo = nueva(db, gerente, servicio=nuevo_servicio(db, gerente, codigo="AB1234"))
    recibo = nueva(db, gerente, recibo="F001-77")

    casos = {
        "luz DEL": catalogo,
        "sedapal": manual,
        "PLAYA": alias,
        "ab 12": codigo,
        "f001-7": recibo,
    }
    for q, deuda in casos.items():
        assert ids(listar(cliente, gerente, q=q)) == [str(deuda.id)], q
    # Los comodines se buscan como texto.
    assert listar(cliente, gerente, q="%")["total"] == 0
    assert listar(cliente, gerente, q="_")["total"] == 0


def test_filtros_por_estado_mes_rango_moneda_categoria_y_servicio(
    cliente: TestClient, db: Session, dos_gerentes: DosGerentes
) -> None:
    gerente = dos_gerentes.uno.gerente
    categoria = nueva_categoria(db, gerente)
    servicio = nuevo_servicio(db, gerente, categoria=categoria)
    septiembre = nueva(db, gerente, vence=date(2026, 9, 10), servicio=servicio)
    octubre = nueva(db, gerente, estado="pagada_parcial", vence=date(2026, 10, 5))
    usd = nueva(db, gerente, moneda="USD", estado="en_proceso", vence=date(2026, 10, 28))
    anulada = nueva(db, gerente, estado="anulada", vence=date(2026, 10, 15))

    def filtrar(**params: Any) -> set[str]:
        return set(ids(listar(cliente, gerente, **params)))

    todas_activas = {str(septiembre.id), str(octubre.id), str(usd.id)}
    assert filtrar() == todas_activas
    assert filtrar(estado="anulada") == {str(anulada.id)}
    assert filtrar(estado=["pendiente", "en_proceso"]) == {str(septiembre.id), str(usd.id)}
    assert filtrar(mes="2026-09") == {str(septiembre.id)}
    assert filtrar(vence_desde="2026-10-01", vence_hasta="2026-10-27") == {str(octubre.id)}
    assert filtrar(moneda="USD") == {str(usd.id)}
    assert filtrar(categoria=str(categoria.id)) == {str(septiembre.id)}
    assert filtrar(servicio=str(servicio.id)) == {str(septiembre.id)}


@pytest.mark.parametrize(
    ("params", "campo"),
    [
        ({"page": 0}, "page"),
        ({"size": 101}, "size"),
        ({"estado": "vencida"}, "estado"),
        ({"estado": ["pendiente", "otro"]}, "estado"),
        ({"moneda": "EUR"}, "moneda"),
        ({"mes": "2026-13"}, "mes"),
        ({"orden": "empresa"}, "orden"),
        ({"categoria": "no-es-uuid"}, "categoria"),
        ({"servicio": "no-es-uuid"}, "servicio"),
        ({"vencida": "quizas"}, "vencida"),
        ({"vence_hasta": "31/10/2026"}, "vence_hasta"),
        ({"q": "x" * 101}, "q"),
        ({"vence_desde": "2026-11-01", "vence_hasta": "2026-10-01"}, "vence_desde"),
    ],
    ids=lambda valor: str(valor)[:30],
)
def test_parametro_invalido_responde_422_con_su_campo(
    cliente: TestClient, dos_gerentes: DosGerentes, params: dict[str, Any], campo: str
) -> None:
    respuesta = cliente.get(RUTA, params=params, headers=cabecera(dos_gerentes.uno.gerente))

    assert respuesta.status_code == 422
    assert respuesta.json()["code"] == "VALIDACION"
    assert respuesta.json()["field"] == campo


def test_las_consultas_no_crecen_con_las_deudas(
    cliente: TestClient, db: Session, dos_gerentes: DosGerentes
) -> None:
    """Totales y página son consultas fijas: no se cargan las deudas una por una."""
    gerente = dos_gerentes.uno.gerente
    sentencias: list[str] = []

    def contar(*args: Any) -> None:
        sentencias.append(args[2])

    def consultas() -> int:
        sentencias.clear()
        event.listen(db.connection(), "before_cursor_execute", contar)
        try:
            listar(cliente, gerente)
        finally:
            event.remove(db.connection(), "before_cursor_execute", contar)
        return len(sentencias)

    nueva(db, gerente)
    pocas = consultas()
    assert any("GROUP BY deuda.moneda" in s for s in sentencias)
    for _ in range(30):
        nueva(db, gerente)

    assert consultas() == pocas
