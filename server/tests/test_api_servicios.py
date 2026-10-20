"""API de servicios (H10, TASK-33): registro, unicidad normalizada, edición, baja y aislamiento.

La carrera de dos registros simultáneos, con transacciones reales, está en
test_servicios_concurrencia.py.
"""

import uuid
from collections.abc import Iterator
from datetime import date
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.errores import ErrorApi
from app.core.seguridad import crear_token
from app.main import app
from app.models import Auditoria, Categoria, Deuda, Empresa, Recurrencia, Servicio, Usuario
from app.services.auditoria import Accion
from app.services.empresas import EMPRESAS_COMUNES, sincronizar_empresas
from app.services.servicios import (
    normalizar_codigo,
    normalizar_nombre,
    servicio_activo_propio,
)
from tests.conftest import DosGerentes, Equipo, nueva_categoria

RUTA = "/api/v1/servicios"
ENEL, CALIDDA, SEDAPAL = (
    next(e for e in EMPRESAS_COMUNES if e.nombre == n) for n in ("Enel", "Cálidda", "Sedapal")
)


@pytest.fixture
def cliente(db: Session) -> Iterator[TestClient]:
    # Sin with: no arranca el ciclo de vida, que se suscribe a Redis y estas rutas no usan.
    sincronizar_empresas(db)
    app.dependency_overrides[get_db] = lambda: db
    yield TestClient(app)
    app.dependency_overrides.clear()


def cabecera(usuario: Usuario) -> dict[str, str]:
    return {"Authorization": f"Bearer {crear_token(usuario)}"}


def datos(categoria: Categoria, **cambios: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "categoria_id": str(categoria.id),
        "empresa_nombre": "Electro Norte",
        "codigo_suministro": uuid.uuid4().hex[:12],
        "lugar_pago": "agente_bcp",
    }
    base.update(cambios)
    return {clave: valor for clave, valor in base.items() if valor is not None}


def crear(cliente: TestClient, usuario: Usuario, cuerpo: dict[str, Any]) -> Any:
    return cliente.post(RUTA, json=cuerpo, headers=cabecera(usuario))


def creado(cliente: TestClient, usuario: Usuario, cuerpo: dict[str, Any]) -> dict[str, Any]:
    r = crear(cliente, usuario, cuerpo)
    assert r.status_code == 201, r.json()
    respuesta: dict[str, Any] = r.json()
    return respuesta


def nuevo_servicio(
    cliente: TestClient, db: Session, equipo: Equipo, **cambios: Any
) -> dict[str, Any]:
    return creado(cliente, equipo.gerente, datos(nueva_categoria(db, equipo.gerente), **cambios))


def error(r: Any) -> tuple[int, str, str | None]:
    cuerpo = r.json()
    return r.status_code, cuerpo["code"], cuerpo["field"]


def deuda_de(
    db: Session, servicio: dict[str, Any], gerente: Usuario, mes: int, estado: str = "pendiente"
) -> Deuda:
    deuda = Deuda(
        gerente_id=gerente.id,
        servicio_id=uuid.UUID(servicio["id"]),
        periodo=date(2026, mes, 1),
        monto=None if estado == "esperando_recibo" else Decimal("50.00"),
        estado=estado,
        fecha_vencimiento=date(2026, mes, 20),
    )
    db.add(deuda)
    db.flush()
    return deuda


def eventos(db: Session, servicio_id: str, accion: Accion) -> list[Auditoria]:
    return list(
        db.scalars(
            select(Auditoria)
            .where(Auditoria.entidad_id == uuid.UUID(servicio_id), Auditoria.accion == accion.value)
            .order_by(Auditoria.creado_en, Auditoria.id)
        )
    )


# Registro (CA01, CA02, CA04 a CA06, CA09)


def test_ca01_ca04_ca05_ca06_registra_un_servicio_de_una_empresa_comun(
    cliente: TestClient, db: Session, dos_gerentes: DosGerentes
) -> None:
    gerente = dos_gerentes.uno.gerente
    categoria = nueva_categoria(db, gerente)

    cuerpo = creado(
        cliente,
        gerente,
        datos(
            categoria,
            empresa_nombre=None,
            empresa_id=str(ENEL.id),
            codigo_suministro=" 1234 5678 ",
            titular=" Rosa Díaz ",
            alias="Luz oficina",
            lugar_pago="agente_kasnet",
            notas="Pagar antes del día 15.",
        ),
    )

    assert (cuerpo["empresa_id"], cuerpo["empresa"], cuerpo["empresa_manual"]) == (
        str(ENEL.id),
        "Enel",
        False,
    )
    assert (cuerpo["codigo_suministro"], cuerpo["titular"], cuerpo["alias"]) == (
        "12345678",
        "Rosa Díaz",
        "Luz oficina",
    )
    assert (cuerpo["lugar_pago"], cuerpo["notas"], cuerpo["estado"]) == (
        "agente_kasnet",
        "Pagar antes del día 15.",
        "activo",
    )
    assert cuerpo["categoria"]["id"] == str(categoria.id)
    assert cuerpo["creado_por"] == str(gerente.id)
    servicio = db.get_one(Servicio, uuid.UUID(cuerpo["id"]))
    assert (servicio.gerente_id, servicio.empresa_nombre, servicio.eliminado_en) == (
        gerente.id,
        None,
        None,
    )
    (evento,) = eventos(db, cuerpo["id"], Accion.SERVICIO_CREADO)
    assert evento.detalle["codigo_suministro"] == "12345678"
    assert evento.detalle["empresa_id"] == str(ENEL.id)


def test_ca01_otra_empresa_se_registra_con_su_nombre_sin_espacios_de_mas(
    cliente: TestClient, db: Session, dos_gerentes: DosGerentes
) -> None:
    cuerpo = nuevo_servicio(cliente, db, dos_gerentes.uno, empresa_nombre="  Electro   Oriente ")

    assert (cuerpo["empresa_id"], cuerpo["empresa"], cuerpo["empresa_manual"]) == (
        None,
        "Electro Oriente",
        True,
    )
    assert cuerpo["titular"] is None and cuerpo["alias"] is None


def test_un_nombre_manual_del_catalogo_se_guarda_como_esa_empresa(
    cliente: TestClient, db: Session, dos_gerentes: DosGerentes
) -> None:
    cuerpo = nuevo_servicio(cliente, db, dos_gerentes.uno, empresa_nombre="CALIDDA")

    assert (cuerpo["empresa_id"], cuerpo["empresa"], cuerpo["empresa_manual"]) == (
        str(CALIDDA.id),
        "Cálidda",
        False,
    )
    assert db.get_one(Servicio, uuid.UUID(cuerpo["id"])).empresa_nombre is None


@pytest.mark.parametrize("tipo", ["servicio_variable", "monto_fijo", "tarjeta", "prestamo"])
def test_ca09_la_asistente_registra_servicios_en_cualquier_categoria(
    cliente: TestClient, db: Session, dos_gerentes: DosGerentes, tipo: str
) -> None:
    equipo = dos_gerentes.uno
    categoria = nueva_categoria(db, equipo.gerente, tipo)

    cuerpo = creado(cliente, equipo.asistente, datos(categoria))

    assert cuerpo["creado_por"] == str(equipo.asistente.id)
    assert db.get_one(Servicio, uuid.UUID(cuerpo["id"])).gerente_id == equipo.gerente.id


def test_ca02_con_patron_el_codigo_debe_cumplir_el_formato_de_la_empresa(
    cliente: TestClient, db: Session, dos_gerentes: DosGerentes
) -> None:
    gerente = dos_gerentes.uno.gerente
    db.get_one(Empresa, SEDAPAL.id).patron_codigo = "[0-9]{7}"
    db.flush()
    categoria = nueva_categoria(db, gerente)
    sedapal = {"empresa_nombre": None, "empresa_id": str(SEDAPAL.id)}

    invalido = crear(cliente, gerente, datos(categoria, codigo_suministro="12345", **sedapal))
    valido = crear(cliente, gerente, datos(categoria, codigo_suministro="123 4567", **sedapal))
    manual = crear(cliente, gerente, datos(categoria, codigo_suministro="12345"))

    assert error(invalido) == (422, "VALIDACION", "codigo_suministro")
    assert "Sedapal" in invalido.json()["detail"]
    assert (valido.status_code, valido.json()["codigo_suministro"]) == (201, "1234567")
    assert manual.status_code == 201


@pytest.mark.parametrize("codigo", ["", "   ", None])
def test_ca02_el_codigo_de_suministro_es_obligatorio(
    cliente: TestClient, db: Session, dos_gerentes: DosGerentes, codigo: str | None
) -> None:
    gerente = dos_gerentes.uno.gerente
    cuerpo = datos(nueva_categoria(db, gerente))
    cuerpo["codigo_suministro"] = codigo
    if codigo is None:
        del cuerpo["codigo_suministro"]

    assert error(crear(cliente, gerente, cuerpo)) == (422, "VALIDACION", "codigo_suministro")


@pytest.mark.parametrize(
    "empresa",
    [{"empresa_id": str(ENEL.id), "empresa_nombre": "Enel"}, {"empresa_nombre": None}],
)
def test_se_indica_una_empresa_del_catalogo_o_un_nombre_no_ambos(
    cliente: TestClient, db: Session, dos_gerentes: DosGerentes, empresa: dict[str, Any]
) -> None:
    gerente = dos_gerentes.uno.gerente

    r = crear(cliente, gerente, datos(nueva_categoria(db, gerente), **empresa))

    assert error(r) == (422, "VALIDACION", "empresa")


def test_una_empresa_inexistente_responde_404(
    cliente: TestClient, db: Session, dos_gerentes: DosGerentes
) -> None:
    gerente = dos_gerentes.uno.gerente
    cuerpo = datos(nueva_categoria(db, gerente), empresa_nombre=None, empresa_id=str(uuid.uuid4()))

    assert error(crear(cliente, gerente, cuerpo)) == (404, "NO_ENCONTRADO", "empresa_id")


@pytest.mark.parametrize(
    ("campo", "valor"),
    [
        ("lugar_pago", None),
        ("lugar_pago", "yape"),
        ("alias", "a" * 61),
        ("titular", "t" * 121),
        ("notas", "n" * 501),
        ("empresa_nombre", "e" * 81),
        ("codigo_suministro", "1" * 41),
    ],
)
def test_ca05_lugar_de_pago_obligatorio_y_largos_maximos(
    cliente: TestClient, db: Session, dos_gerentes: DosGerentes, campo: str, valor: str | None
) -> None:
    gerente = dos_gerentes.uno.gerente
    cuerpo = datos(nueva_categoria(db, gerente))
    if valor is None:
        del cuerpo[campo]
    else:
        cuerpo[campo] = valor

    assert error(crear(cliente, gerente, cuerpo)) == (422, "VALIDACION", campo)


def test_banca_movil_representa_banca_movil_y_yape(
    cliente: TestClient, db: Session, dos_gerentes: DosGerentes
) -> None:
    cuerpo = nuevo_servicio(cliente, db, dos_gerentes.uno, lugar_pago="banca_movil")

    assert cuerpo["lugar_pago"] == "banca_movil"


def test_una_categoria_de_otro_gerente_responde_404(
    cliente: TestClient, db: Session, dos_gerentes: DosGerentes
) -> None:
    ajena = nueva_categoria(db, dos_gerentes.dos.gerente)

    r = crear(cliente, dos_gerentes.uno.asistente, datos(ajena))

    assert error(r) == (404, "NO_ENCONTRADO", "categoria_id")


# Unicidad normalizada (CA03)


@pytest.mark.parametrize(
    ("primero", "segundo"),
    [
        (
            {"empresa_id": str(ENEL.id), "codigo_suministro": "1234AB"},
            {"empresa_id": str(ENEL.id), "codigo_suministro": " 12 34 ab "},
        ),
        (
            {"empresa_nombre": "Luz Norte", "codigo_suministro": "555"},
            {"empresa_nombre": "  LUZ   NORTE ", "codigo_suministro": "5 5 5"},
        ),
        (
            {"empresa_nombre": "calidda", "codigo_suministro": "777"},
            {"empresa_id": str(CALIDDA.id), "codigo_suministro": "777"},
        ),
        (
            {"empresa_id": str(CALIDDA.id), "codigo_suministro": "778"},
            {"empresa_nombre": "Cálidda", "codigo_suministro": "778"},
        ),
    ],
)
def test_ca03_la_misma_empresa_y_codigo_normalizados_se_rechazan(
    cliente: TestClient,
    db: Session,
    dos_gerentes: DosGerentes,
    primero: dict[str, Any],
    segundo: dict[str, Any],
) -> None:
    equipo = dos_gerentes.uno
    categoria = nueva_categoria(db, equipo.gerente)
    sin_nombre = {"empresa_nombre": None}
    creado(cliente, equipo.gerente, datos(categoria, **(sin_nombre | primero)))

    r = crear(cliente, equipo.asistente, datos(categoria, **(sin_nombre | segundo)))

    assert error(r) == (409, "DUPLICADO", "codigo_suministro")


def test_ca03_el_mismo_codigo_con_otra_empresa_si_se_permite(
    cliente: TestClient, db: Session, dos_gerentes: DosGerentes
) -> None:
    equipo = dos_gerentes.uno
    nuevo_servicio(cliente, db, equipo, empresa_nombre="Luz Norte", codigo_suministro="900")

    otra = nuevo_servicio(cliente, db, equipo, empresa_nombre="Luz Sur", codigo_suministro="900")

    assert otra["codigo_suministro"] == "900"


def test_ca03_otro_gerente_registra_la_misma_empresa_y_codigo(
    cliente: TestClient, db: Session, dos_gerentes: DosGerentes
) -> None:
    cuerpo = {"empresa_nombre": None, "empresa_id": str(ENEL.id), "codigo_suministro": "42"}
    nuevo_servicio(cliente, db, dos_gerentes.uno, **cuerpo)

    otro = nuevo_servicio(cliente, db, dos_gerentes.dos, **cuerpo)

    assert otro["codigo_suministro"] == "42"


def test_ca03_un_servicio_de_baja_sigue_ocupando_su_codigo(
    cliente: TestClient, db: Session, dos_gerentes: DosGerentes
) -> None:
    equipo = dos_gerentes.uno
    servicio = nuevo_servicio(cliente, db, equipo, codigo_suministro="321")
    cliente.post(f"{RUTA}/{servicio['id']}/baja", headers=cabecera(equipo.gerente))

    r = crear(
        cliente, equipo.gerente, datos(nueva_categoria(db, equipo.gerente), codigo_suministro="321")
    )

    assert error(r) == (409, "DUPLICADO", "codigo_suministro")


# Lista y detalle (CA10)


def test_ca10_lista_con_busqueda_filtro_por_categoria_y_paginacion(
    cliente: TestClient, db: Session, dos_gerentes: DosGerentes
) -> None:
    equipo = dos_gerentes.uno
    luz, agua = nueva_categoria(db, equipo.gerente), nueva_categoria(db, equipo.gerente)
    oficina = creado(cliente, equipo.gerente, datos(luz, alias="Oficina", titular="Rosa Díaz"))
    casa = creado(
        cliente,
        equipo.gerente,
        datos(luz, alias="casa", empresa_nombre=None, empresa_id=str(ENEL.id)),
    )
    almacen = creado(
        cliente, equipo.asistente, datos(agua, alias="Almacén", codigo_suministro="AB-778")
    )
    nuevo_servicio(cliente, db, dos_gerentes.dos, alias="Oficina")

    def listar(**parametros: Any) -> dict[str, Any]:
        r = cliente.get(RUTA, params=parametros, headers=cabecera(equipo.asistente))
        assert r.status_code == 200, r.json()
        cuerpo: dict[str, Any] = r.json()
        return cuerpo

    def ids(cuerpo: dict[str, Any]) -> list[str]:
        return [item["id"] for item in cuerpo["items"]]

    todos = listar()
    assert ids(todos) == [almacen["id"], casa["id"], oficina["id"]]
    assert (todos["total"], todos["page"]) == (3, 1)
    assert ids(listar(categoria_id=str(luz.id))) == [casa["id"], oficina["id"]]
    assert ids(listar(q="ofic")) == [oficina["id"]]
    assert ids(listar(q="díaz")) == [oficina["id"]]
    assert ids(listar(q="enel")) == [casa["id"]]
    assert ids(listar(q="b-77")) == [almacen["id"]]
    assert ids(listar(q="100%")) == []
    segunda = listar(size=2, page=2)
    assert (ids(segunda), segunda["total"]) == ([oficina["id"]], 3)


def test_la_lista_muestra_activos_por_defecto_y_filtra_por_estado(
    cliente: TestClient, db: Session, dos_gerentes: DosGerentes
) -> None:
    equipo = dos_gerentes.uno
    activo = nuevo_servicio(cliente, db, equipo, alias="A")
    de_baja = nuevo_servicio(cliente, db, equipo, alias="B")
    cliente.post(f"{RUTA}/{de_baja['id']}/baja", headers=cabecera(equipo.gerente))

    def ids(**parametros: Any) -> list[str]:
        r = cliente.get(RUTA, params=parametros, headers=cabecera(equipo.gerente))
        return [item["id"] for item in r.json()["items"]]

    assert ids() == [activo["id"]]
    assert ids(estado="baja") == [de_baja["id"]]
    assert ids(estado="todos") == [activo["id"], de_baja["id"]]
    r = cliente.get(RUTA, params={"estado": "eliminado"}, headers=cabecera(equipo.gerente))
    assert error(r) == (422, "VALIDACION", "estado")


def test_filtrar_por_una_categoria_de_otro_gerente_responde_404(
    cliente: TestClient, db: Session, dos_gerentes: DosGerentes
) -> None:
    ajena = nueva_categoria(db, dos_gerentes.dos.gerente)

    r = cliente.get(
        RUTA, params={"categoria_id": str(ajena.id)}, headers=cabecera(dos_gerentes.uno.gerente)
    )

    assert error(r) == (404, "NO_ENCONTRADO", "categoria_id")


def test_ca07_el_detalle_cuenta_las_deudas_pendientes(
    cliente: TestClient, db: Session, dos_gerentes: DosGerentes
) -> None:
    equipo = dos_gerentes.uno
    servicio = nuevo_servicio(cliente, db, equipo)
    for mes, estado in enumerate(("pendiente", "esperando_recibo", "pagada", "anulada"), start=1):
        deuda_de(db, servicio, equipo.gerente, mes, estado)

    r = cliente.get(f"{RUTA}/{servicio['id']}", headers=cabecera(equipo.asistente))

    assert r.status_code == 200
    assert (r.json()["id"], r.json()["deudas_pendientes"]) == (servicio["id"], 2)


def test_otro_gerente_no_ve_ni_modifica_el_servicio(
    cliente: TestClient, db: Session, dos_gerentes: DosGerentes
) -> None:
    servicio = nuevo_servicio(cliente, db, dos_gerentes.uno)
    otro = dos_gerentes.dos
    ruta = f"{RUTA}/{servicio['id']}"
    cuerpo = datos(nueva_categoria(db, otro.gerente))

    respuestas = [
        cliente.get(ruta, headers=cabecera(otro.asistente)),
        cliente.put(ruta, json=cuerpo, headers=cabecera(otro.asistente)),
        cliente.post(f"{ruta}/baja", headers=cabecera(otro.gerente)),
        cliente.post(f"{ruta}/reactivar", headers=cabecera(otro.gerente)),
    ]

    assert [error(r)[:2] for r in respuestas] == [(404, "NO_ENCONTRADO")] * 4
    assert db.get_one(Servicio, uuid.UUID(servicio["id"])).estado == "activo"
    assert cliente.get(f"{RUTA}/{uuid.uuid4()}", headers=cabecera(otro.gerente)).status_code == 404


def test_sin_sesion_responde_401(cliente: TestClient) -> None:
    assert error(cliente.get(RUTA))[:2] == (401, "NO_AUTENTICADO")


# Edición (CA07)


def test_ca07_cambiar_el_codigo_informa_las_deudas_pendientes_y_no_las_toca(
    cliente: TestClient, db: Session, dos_gerentes: DosGerentes
) -> None:
    equipo = dos_gerentes.uno
    categoria = nueva_categoria(db, equipo.gerente)
    servicio = creado(cliente, equipo.gerente, datos(categoria, codigo_suministro="111"))
    pendiente = deuda_de(db, servicio, equipo.gerente, 1)
    deuda_de(db, servicio, equipo.gerente, 2, "en_proceso")
    deuda_de(db, servicio, equipo.gerente, 3, "pagada")

    r = cliente.put(
        f"{RUTA}/{servicio['id']}",
        json=datos(categoria, codigo_suministro="222"),
        headers=cabecera(equipo.asistente),
    )

    assert r.status_code == 200, r.json()
    assert r.json()["codigo_suministro"] == "222"
    assert r.json()["advertencias"] == {"codigo_cambiado": True, "deudas_pendientes": 2}
    db.refresh(pendiente)
    assert (pendiente.estado, pendiente.monto) == ("pendiente", Decimal("50.00"))
    (evento,) = eventos(db, servicio["id"], Accion.SERVICIO_ACTUALIZADO)
    assert evento.usuario_id == equipo.asistente.id
    assert evento.detalle["codigo_suministro"] == {"anterior": "111", "nuevo": "222"}
    assert evento.detalle["deudas_pendientes"] == 2


def test_editar_sin_cambiar_el_codigo_no_lo_advierte(
    cliente: TestClient, db: Session, dos_gerentes: DosGerentes
) -> None:
    equipo = dos_gerentes.uno
    categoria, otra = nueva_categoria(db, equipo.gerente), nueva_categoria(db, equipo.gerente)
    servicio = creado(cliente, equipo.gerente, datos(categoria, codigo_suministro="333"))
    deuda_de(db, servicio, equipo.gerente, 1)

    r = cliente.put(
        f"{RUTA}/{servicio['id']}",
        json=datos(otra, codigo_suministro=" 3 3 3 ", alias="Nuevo alias", lugar_pago="otro"),
        headers=cabecera(equipo.gerente),
    )

    assert r.status_code == 200, r.json()
    cuerpo = r.json()
    assert cuerpo["advertencias"] == {"codigo_cambiado": False, "deudas_pendientes": 1}
    assert (cuerpo["alias"], cuerpo["lugar_pago"], cuerpo["categoria"]["id"]) == (
        "Nuevo alias",
        "otro",
        str(otra.id),
    )
    (evento,) = eventos(db, servicio["id"], Accion.SERVICIO_ACTUALIZADO)
    assert "codigo_suministro" not in evento.detalle and "deudas_pendientes" not in evento.detalle


def test_guardar_sin_cambios_no_registra_auditoria(
    cliente: TestClient, db: Session, dos_gerentes: DosGerentes
) -> None:
    equipo = dos_gerentes.uno
    categoria = nueva_categoria(db, equipo.gerente)
    cuerpo = datos(categoria, codigo_suministro="444")
    servicio = creado(cliente, equipo.gerente, cuerpo)

    r = cliente.put(f"{RUTA}/{servicio['id']}", json=cuerpo, headers=cabecera(equipo.gerente))

    assert r.status_code == 200
    assert eventos(db, servicio["id"], Accion.SERVICIO_ACTUALIZADO) == []


def test_editar_hacia_un_codigo_ocupado_responde_409_y_no_cambia_nada(
    cliente: TestClient, db: Session, dos_gerentes: DosGerentes
) -> None:
    equipo = dos_gerentes.uno
    categoria = nueva_categoria(db, equipo.gerente)
    creado(cliente, equipo.gerente, datos(categoria, codigo_suministro="555"))
    servicio = creado(cliente, equipo.gerente, datos(categoria, codigo_suministro="556"))

    r = cliente.put(
        f"{RUTA}/{servicio['id']}",
        json=datos(categoria, codigo_suministro="55 5"),
        headers=cabecera(equipo.gerente),
    )

    assert error(r) == (409, "DUPLICADO", "codigo_suministro")
    assert db.get_one(Servicio, uuid.UUID(servicio["id"])).codigo_suministro == "556"


def test_editar_un_servicio_de_baja_responde_409(
    cliente: TestClient, db: Session, dos_gerentes: DosGerentes
) -> None:
    equipo = dos_gerentes.uno
    categoria = nueva_categoria(db, equipo.gerente)
    servicio = creado(cliente, equipo.gerente, datos(categoria))
    cliente.post(f"{RUTA}/{servicio['id']}/baja", headers=cabecera(equipo.gerente))

    r = cliente.put(
        f"{RUTA}/{servicio['id']}", json=datos(categoria), headers=cabecera(equipo.asistente)
    )

    assert error(r)[:2] == (409, "SERVICIO_DE_BAJA")


# Baja y reactivación (CA08)


def test_ca08_la_baja_detiene_las_recurrencias_y_conserva_las_deudas_pendientes(
    cliente: TestClient, db: Session, dos_gerentes: DosGerentes
) -> None:
    equipo = dos_gerentes.uno
    servicio = nuevo_servicio(cliente, db, equipo)
    servicio_id = uuid.UUID(servicio["id"])
    recurrencia = Recurrencia(
        servicio_id=servicio_id, tipo="monto_fijo", monto=Decimal("80.00"), dia_vencimiento=31
    )
    db.add(recurrencia)
    db.flush()
    pendiente = deuda_de(db, servicio, equipo.gerente, 1)
    en_proceso = deuda_de(db, servicio, equipo.gerente, 2, "en_proceso")
    deuda_de(db, servicio, equipo.gerente, 3, "pagada")

    r = cliente.post(f"{RUTA}/{servicio_id}/baja", headers=cabecera(equipo.gerente))

    assert r.status_code == 200, r.json()
    cuerpo = r.json()
    assert (cuerpo["estado"], cuerpo["recurrencias_desactivadas"], cuerpo["deudas_pendientes"]) == (
        "baja",
        1,
        2,
    )
    db.refresh(recurrencia)
    assert recurrencia.activa is False
    for deuda, estado in ((pendiente, "pendiente"), (en_proceso, "en_proceso")):
        db.refresh(deuda)
        assert (deuda.estado, deuda.monto) == (estado, Decimal("50.00"))
    assert db.get_one(Servicio, servicio_id).eliminado_en is None
    bandeja = cliente.get("/api/v1/bandeja", headers=cabecera(equipo.asistente)).json()
    assert str(pendiente.id) in [item["id"] for item in bandeja["items"]]
    detalle = cliente.get(f"{RUTA}/{servicio_id}", headers=cabecera(equipo.asistente)).json()
    assert (detalle["estado"], detalle["deudas_pendientes"]) == ("baja", 2)
    (evento,) = eventos(db, servicio["id"], Accion.SERVICIO_DADO_DE_BAJA)
    assert evento.detalle == {"recurrencias_desactivadas": 1, "deudas_pendientes": 2}


def test_dar_de_baja_sin_recurrencia_ni_deudas(
    cliente: TestClient, db: Session, dos_gerentes: DosGerentes
) -> None:
    equipo = dos_gerentes.uno
    servicio = nuevo_servicio(cliente, db, equipo)

    r = cliente.post(f"{RUTA}/{servicio['id']}/baja", headers=cabecera(equipo.gerente))

    assert (r.json()["recurrencias_desactivadas"], r.json()["deudas_pendientes"]) == (0, 0)


def test_dar_de_baja_dos_veces_responde_409(
    cliente: TestClient, db: Session, dos_gerentes: DosGerentes
) -> None:
    equipo = dos_gerentes.uno
    servicio = nuevo_servicio(cliente, db, equipo)
    ruta = f"{RUTA}/{servicio['id']}/baja"
    cliente.post(ruta, headers=cabecera(equipo.gerente))

    assert error(cliente.post(ruta, headers=cabecera(equipo.gerente)))[:2] == (
        409,
        "SERVICIO_DE_BAJA",
    )
    assert len(eventos(db, servicio["id"], Accion.SERVICIO_DADO_DE_BAJA)) == 1


@pytest.mark.parametrize("accion", ["baja", "reactivar"])
def test_solo_el_gerente_da_de_baja_y_reactiva(
    cliente: TestClient, db: Session, dos_gerentes: DosGerentes, accion: str
) -> None:
    equipo = dos_gerentes.uno
    servicio = nuevo_servicio(cliente, db, equipo)

    r = cliente.post(f"{RUTA}/{servicio['id']}/{accion}", headers=cabecera(equipo.asistente))

    assert error(r)[:2] == (403, "SIN_PERMISO")
    assert db.get_one(Servicio, uuid.UUID(servicio["id"])).estado == "activo"


def test_reactivar_no_reactiva_las_recurrencias(
    cliente: TestClient, db: Session, dos_gerentes: DosGerentes
) -> None:
    equipo = dos_gerentes.uno
    servicio = nuevo_servicio(cliente, db, equipo)
    recurrencia = Recurrencia(
        servicio_id=uuid.UUID(servicio["id"]), tipo="variable", dia_vencimiento=10
    )
    db.add(recurrencia)
    db.flush()
    cliente.post(f"{RUTA}/{servicio['id']}/baja", headers=cabecera(equipo.gerente))

    r = cliente.post(f"{RUTA}/{servicio['id']}/reactivar", headers=cabecera(equipo.gerente))

    assert (r.status_code, r.json()["estado"]) == (200, "activo")
    db.refresh(recurrencia)
    assert recurrencia.activa is False
    assert len(eventos(db, servicio["id"], Accion.SERVICIO_REACTIVADO)) == 1
    otra_vez = cliente.post(f"{RUTA}/{servicio['id']}/reactivar", headers=cabecera(equipo.gerente))
    assert error(otra_vez)[:2] == (409, "CONFLICTO")


def test_un_servicio_de_baja_no_admite_deudas_nuevas(
    cliente: TestClient, db: Session, dos_gerentes: DosGerentes
) -> None:
    """Contrato para TASK-38: el registro manual usa servicio_activo_propio."""
    equipo = dos_gerentes.uno
    servicio = nuevo_servicio(cliente, db, equipo)
    servicio_id = uuid.UUID(servicio["id"])
    assert servicio_activo_propio(db, servicio_id, equipo.gerente.id).id == servicio_id
    cliente.post(f"{RUTA}/{servicio_id}/baja", headers=cabecera(equipo.gerente))

    with pytest.raises(ErrorApi) as baja:
        servicio_activo_propio(db, servicio_id, equipo.gerente.id)
    with pytest.raises(ErrorApi) as ajeno:
        servicio_activo_propio(db, servicio_id, dos_gerentes.dos.gerente.id)

    assert (baja.value.status_code, baja.value.code) == (409, "SERVICIO_DE_BAJA")
    assert (ajeno.value.status_code, ajeno.value.code) == (404, "NO_ENCONTRADO")


# Normalización


@pytest.mark.parametrize(
    ("escrito", "normal"),
    [(" 12 34-ab ", "1234-AB"), ("\t9876\n", "9876"), ("abc", "ABC"), ("   ", "")],
)
def test_normalizar_codigo_quita_espacios_y_pasa_a_mayusculas(escrito: str, normal: str) -> None:
    assert normalizar_codigo(escrito) == normal


def test_normalizar_nombre_colapsa_espacios_y_conserva_acentos() -> None:
    assert normalizar_nombre("  Electro   Oriénte ") == "Electro Oriénte"
