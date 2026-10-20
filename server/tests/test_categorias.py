from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.seguridad import crear_token
from app.main import app
from app.models import Auditoria, Categoria, Servicio, Usuario
from tests.conftest import DosGerentes

CATEGORIAS_URL = "/api/v1/categorias"
IP = "203.0.113.25"


def auth_headers(usuario: Usuario) -> dict[str, str]:
    return {"Authorization": f"Bearer {crear_token(usuario)}"}


@pytest.fixture
def cliente(db: Session) -> Iterator[TestClient]:
    app.dependency_overrides[get_db] = lambda: db
    yield TestClient(app, client=(IP, 50000))
    app.dependency_overrides.pop(get_db, None)


def crear_servicio_de_prueba(
    db: Session,
    gerente: Usuario,
    categoria: Categoria,
    codigo: str = "SUM-100",
    activo: bool = True,
) -> Servicio:
    from datetime import UTC, datetime

    servicio = Servicio(
        gerente_id=gerente.id,
        categoria_id=categoria.id,
        empresa_nombre="Empresa Test",
        codigo_suministro=codigo,
        lugar_pago="banca_movil",
        estado="activo" if activo else "baja",
        eliminado_en=None if activo else datetime.now(UTC),
    )
    db.add(servicio)
    db.commit()
    db.refresh(servicio)
    return servicio


def test_ca04_crear_categoria_gerente_y_asistente(
    cliente: TestClient,
    dos_gerentes: DosGerentes,
    db: Session,
) -> None:
    """CA04: Tanto el gerente como la asistente pueden crear categorías."""
    gerente = dos_gerentes.uno.gerente
    asistente = dos_gerentes.uno.asistente

    # 1. Gerente crea categoría
    payload_gerente = {
        "nombre": "Mantenimiento Hogar",
        "color": "#10B981",
        "icono": "pi-home",
        "tipo": "servicio_variable",
    }
    r1 = cliente.post(CATEGORIAS_URL, json=payload_gerente, headers=auth_headers(gerente))
    assert r1.status_code == 201, r1.text
    data1 = r1.json()
    assert data1["nombre"] == "Mantenimiento Hogar"
    assert data1["color"] == "#10B981"
    assert data1["tipo"] == "servicio_variable"
    assert data1["cantidad_servicios"] == 0

    # 2. Asistente crea categoría para el mismo gerente
    payload_asistente = {
        "nombre": "Cursos Online",
        "color": "#6366F1",
        "icono": "pi-book",
        "tipo": "monto_fijo",
    }
    r2 = cliente.post(CATEGORIAS_URL, json=payload_asistente, headers=auth_headers(asistente))
    assert r2.status_code == 201, r2.text
    data2 = r2.json()
    assert data2["nombre"] == "Cursos Online"
    assert data2["creado_por"] == str(asistente.id)

    # Verificar que ambas pertenecen al mismo gerente
    cat_asistente = db.get(Categoria, data2["id"])
    assert cat_asistente is not None
    assert cat_asistente.gerente_id == gerente.id

    # 3. Usuario sin autenticar -> 401
    r_unauth = cliente.post(CATEGORIAS_URL, json=payload_gerente)
    assert r_unauth.status_code == 401


def test_ca04_asistente_no_puede_editar_ni_eliminar_categoria(
    cliente: TestClient,
    dos_gerentes: DosGerentes,
) -> None:
    """CA04: La asistente tiene prohibido editar o eliminar categorías (403 SIN_PERMISO)."""
    gerente = dos_gerentes.uno.gerente
    asistente = dos_gerentes.uno.asistente

    # Crear categoría como gerente
    r_crear = cliente.post(
        CATEGORIAS_URL,
        json={"nombre": "Salud", "tipo": "monto_fijo"},
        headers=auth_headers(gerente),
    )
    assert r_crear.status_code == 201
    cat_id = r_crear.json()["id"]

    # Asistente intenta editar -> 403
    r_edit = cliente.put(
        f"{CATEGORIAS_URL}/{cat_id}",
        json={"nombre": "Salud Modificada"},
        headers=auth_headers(asistente),
    )
    assert r_edit.status_code == 403
    assert r_edit.json()["code"] == "SIN_PERMISO"

    # Asistente intenta mover servicios -> 403
    r_mover = cliente.post(
        f"{CATEGORIAS_URL}/{cat_id}/mover-servicios",
        json={"destino_id": cat_id},
        headers=auth_headers(asistente),
    )
    assert r_mover.status_code == 403
    assert r_mover.json()["code"] == "SIN_PERMISO"

    # Asistente intenta eliminar -> 403
    r_del = cliente.delete(f"{CATEGORIAS_URL}/{cat_id}", headers=auth_headers(asistente))
    assert r_del.status_code == 403
    assert r_del.json()["code"] == "SIN_PERMISO"


def test_ca04_gerente_edita_categoria_exitosamente(
    cliente: TestClient,
    dos_gerentes: DosGerentes,
    db: Session,
) -> None:
    """CA04: El gerente puede editar los datos de su categoría."""
    gerente = dos_gerentes.uno.gerente
    headers = auth_headers(gerente)

    r_crear = cliente.post(
        CATEGORIAS_URL,
        json={"nombre": "Educacion", "color": "#000000", "tipo": "monto_fijo"},
        headers=headers,
    )
    cat_id = r_crear.json()["id"]

    r_put = cliente.put(
        f"{CATEGORIAS_URL}/{cat_id}",
        json={"nombre": "Educación Superior", "color": "#3B82F6", "tipo": "servicio_variable"},
        headers=headers,
    )
    assert r_put.status_code == 200
    data = r_put.json()
    assert data["nombre"] == "Educación Superior"
    assert data["color"] == "#3B82F6"
    assert data["tipo"] == "servicio_variable"

    # Auditoría registrada
    ev = db.scalar(
        select(Auditoria).where(
            Auditoria.entidad_id == cat_id,
            Auditoria.accion == "categoria_actualizada",
        )
    )
    assert ev is not None


def test_ca05_eliminar_categoria_sin_servicios(
    cliente: TestClient,
    dos_gerentes: DosGerentes,
    db: Session,
) -> None:
    """CA05: Una categoría sin servicios se elimina directamente."""
    gerente = dos_gerentes.uno.gerente
    headers = auth_headers(gerente)

    r_crear = cliente.post(
        CATEGORIAS_URL,
        json={"nombre": "Temporal", "tipo": "monto_fijo"},
        headers=headers,
    )
    cat_id = r_crear.json()["id"]

    r_del = cliente.delete(f"{CATEGORIAS_URL}/{cat_id}", headers=headers)
    assert r_del.status_code == 200
    assert r_del.json()["servicios_movidos"] == 0

    # Ya no existe
    r_get = cliente.get(f"{CATEGORIAS_URL}/{cat_id}", headers=headers)
    assert r_get.status_code == 404

    # Auditoría registrada
    ev = db.scalar(
        select(Auditoria).where(
            Auditoria.entidad_id == cat_id,
            Auditoria.accion == "categoria_eliminada",
        )
    )
    assert ev is not None


def test_ca05_eliminar_categoria_con_servicios_exige_mover(
    cliente: TestClient,
    dos_gerentes: DosGerentes,
    db: Session,
) -> None:
    """CA05: No se puede eliminar si tiene servicios; primero se deben mover."""
    gerente = dos_gerentes.uno.gerente
    headers = auth_headers(gerente)

    # Crear dos categorías
    r1 = cliente.post(
        CATEGORIAS_URL,
        json={"nombre": "Streaming Antiguo", "tipo": "monto_fijo"},
        headers=headers,
    )
    cat_origen_id = r1.json()["id"]

    r2 = cliente.post(
        CATEGORIAS_URL,
        json={"nombre": "Entretenimiento Nuevo", "tipo": "monto_fijo"},
        headers=headers,
    )
    cat_destino_id = r2.json()["id"]

    cat_origen = db.get(Categoria, cat_origen_id)
    assert cat_origen is not None

    # Asociar dos servicios a la categoría origen
    s1 = crear_servicio_de_prueba(db, gerente, cat_origen, codigo="NET-001")
    s2 = crear_servicio_de_prueba(db, gerente, cat_origen, codigo="DIS-002")

    # 1. Intento de eliminar sin mover_a -> 409 CATEGORIA_CON_SERVICIOS
    r_del_fallo = cliente.delete(f"{CATEGORIAS_URL}/{cat_origen_id}", headers=headers)
    assert r_del_fallo.status_code == 409
    assert r_del_fallo.json()["code"] == "CATEGORIA_CON_SERVICIOS"

    # 2. Eliminar especificando mover_a -> 200 OK y servicios traspasados
    r_del_exito = cliente.delete(
        f"{CATEGORIAS_URL}/{cat_origen_id}?mover_a={cat_destino_id}",
        headers=headers,
    )
    assert r_del_exito.status_code == 200
    assert r_del_exito.json()["servicios_movidos"] == 2

    # Verificar en la base de datos que los servicios ahora pertenecen a la categoría destino
    db.refresh(s1)
    db.refresh(s2)
    assert str(s1.categoria_id) == str(cat_destino_id)
    assert str(s2.categoria_id) == str(cat_destino_id)

    # La categoría origen ya no existe
    assert db.get(Categoria, cat_origen_id) is None


def test_ca05_mover_servicios_endpoint_dedicado(
    cliente: TestClient,
    dos_gerentes: DosGerentes,
    db: Session,
) -> None:
    """CA05: Mover servicios mediante endpoint POST /{id}/mover-servicios."""
    gerente = dos_gerentes.uno.gerente
    headers = auth_headers(gerente)

    r1 = cliente.post(
        CATEGORIAS_URL, json={"nombre": "Origen", "tipo": "monto_fijo"}, headers=headers
    )
    r2 = cliente.post(
        CATEGORIAS_URL, json={"nombre": "Destino", "tipo": "monto_fijo"}, headers=headers
    )
    cat_origen_id = r1.json()["id"]
    cat_destino_id = r2.json()["id"]

    cat_origen = db.get(Categoria, cat_origen_id)
    assert cat_origen is not None
    s1 = crear_servicio_de_prueba(db, gerente, cat_origen, codigo="SRV-1")

    # Traspasar servicios
    r_mover = cliente.post(
        f"{CATEGORIAS_URL}/{cat_origen_id}/mover-servicios",
        json={"destino_id": cat_destino_id},
        headers=headers,
    )
    assert r_mover.status_code == 200
    assert r_mover.json()["servicios_movidos"] == 1

    db.refresh(s1)
    assert str(s1.categoria_id) == str(cat_destino_id)

    # Ahora origen tiene 0 servicios y se puede eliminar sin mover_a
    r_del = cliente.delete(f"{CATEGORIAS_URL}/{cat_origen_id}", headers=headers)
    assert r_del.status_code == 200


def test_conteo_de_servicios_en_listado(
    cliente: TestClient,
    dos_gerentes: DosGerentes,
    db: Session,
) -> None:
    """El listado informa la cantidad de servicios activos por categoría."""
    gerente = dos_gerentes.uno.gerente
    headers = auth_headers(gerente)

    r = cliente.post(
        CATEGORIAS_URL, json={"nombre": "Telefonia", "tipo": "servicio_variable"}, headers=headers
    )
    cat_id = r.json()["id"]
    cat = db.get(Categoria, cat_id)
    assert cat is not None

    # Agregar 1 servicio activo y 1 servicio eliminado
    crear_servicio_de_prueba(db, gerente, cat, codigo="ACT-1", activo=True)
    crear_servicio_de_prueba(db, gerente, cat, codigo="DEL-2", activo=False)

    # Consultar listado
    r_list = cliente.get(CATEGORIAS_URL, headers=headers)
    assert r_list.status_code == 200
    categorias = r_list.json()

    encontrada = next((c for c in categorias if c["id"] == str(cat_id)), None)
    assert encontrada is not None
    # Solo cuenta el servicio activo
    assert encontrada["cantidad_servicios"] == 1


def test_rechazo_nombre_categoria_duplicado(
    cliente: TestClient,
    dos_gerentes: DosGerentes,
) -> None:
    """Rechaza nombres duplicados para el mismo gerente (409 CATEGORIA_DUPLICADA)."""
    gerente = dos_gerentes.uno.gerente
    headers = auth_headers(gerente)

    r1 = cliente.post(
        CATEGORIAS_URL, json={"nombre": "Seguros", "tipo": "monto_fijo"}, headers=headers
    )
    assert r1.status_code == 201

    # Intentar crear con mismo nombre en minúsculas
    r2 = cliente.post(
        CATEGORIAS_URL, json={"nombre": "seguros", "tipo": "monto_fijo"}, headers=headers
    )
    assert r2.status_code == 409
    assert r2.json()["code"] == "CATEGORIA_DUPLICADA"


def test_aislamiento_entre_gerentes(
    cliente: TestClient,
    dos_gerentes: DosGerentes,
) -> None:
    """Un gerente no puede ver ni modificar categorías de otro gerente."""
    gerente_uno = dos_gerentes.uno.gerente
    gerente_dos = dos_gerentes.dos.gerente

    r1 = cliente.post(
        CATEGORIAS_URL,
        json={"nombre": "Privada Uno", "tipo": "monto_fijo"},
        headers=auth_headers(gerente_uno),
    )
    cat_uno_id = r1.json()["id"]

    # Gerente dos no puede obtenerla
    r_get = cliente.get(f"{CATEGORIAS_URL}/{cat_uno_id}", headers=auth_headers(gerente_dos))
    assert r_get.status_code == 404

    # Gerente dos no puede editarla
    r_edit = cliente.put(
        f"{CATEGORIAS_URL}/{cat_uno_id}",
        json={"nombre": "Hack"},
        headers=auth_headers(gerente_dos),
    )
    assert r_edit.status_code == 404

    # Gerente dos no puede eliminarla
    r_del = cliente.delete(f"{CATEGORIAS_URL}/{cat_uno_id}", headers=auth_headers(gerente_dos))
    assert r_del.status_code == 404
