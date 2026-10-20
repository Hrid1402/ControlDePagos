"""Pruebas de verificación de cuentas de asistente y restricción de única activa (TASK-12).

Cubre los criterios de aceptación:
CA02: Solo puede haber una cuenta activa a la vez por gerente, y se destaca en la lista.
CA17: El detalle muestra datos, estado, fecha de creación e historial de activaciones.
Aceptación: Dos solicitudes simultáneas nunca dejan dos asistentes activas;
la consulta del gerente no cruza cuentas ajenas.
"""

import uuid
from collections.abc import Iterator
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.seguridad import crear_token
from app.core.tiempo import ahora_lima
from app.main import app
from app.models import Usuario
from app.services.asistentes import consulta_lista
from tests.conftest import DosGerentes

URL = "/api/v1/asistentes"


def auth_headers(usuario: Usuario) -> dict[str, str]:
    return {"Authorization": f"Bearer {crear_token(usuario)}"}


@pytest.fixture
def cliente(db: Session) -> Iterator[TestClient]:
    app.dependency_overrides[get_db] = lambda: db
    yield TestClient(app)
    app.dependency_overrides.pop(get_db, None)


def crear_asistente_modelo(
    db: Session,
    gerente: Usuario,
    nombre: str,
    *,
    estado: str = "inactiva",
    horas_atras: int = 1,
    **campos: object,
) -> Usuario:
    asistente = Usuario(
        rol="asistente",
        gerente_id=gerente.id,
        username=f"{nombre.lower()}_{uuid.uuid4().hex[:6]}",
        password_hash="hash_de_prueba",
        nombres=nombre,
        apellidos="Gómez",
        estado=estado,
        creado_en=ahora_lima() - timedelta(hours=horas_atras),
        **campos,
    )
    db.add(asistente)
    db.flush()
    return asistente


def test_ca02_restriccion_sql_uq_usuario_asistente_activa(
    db: Session,
    dos_gerentes: DosGerentes,
) -> None:
    """CA02: La BD rechaza insertar dos asistentes activas para el mismo gerente
    usando la restricción uq_usuario_asistente_activa.
    """
    gerente1 = dos_gerentes.uno.gerente
    gerente2 = dos_gerentes.dos.gerente

    # gerente1 ya tiene una asistente activa proveniente del fixture dos_gerentes
    asistente_activa_g1 = dos_gerentes.uno.asistente
    assert asistente_activa_g1.estado == "activa"
    assert asistente_activa_g1.gerente_id == gerente1.id

    # Intentar insertar una segunda asistente activa directamente en BD para gerente1 debe fallar
    segunda_activa_g1 = Usuario(
        rol="asistente",
        gerente_id=gerente1.id,
        username=f"activa2_{uuid.uuid4().hex[:6]}",
        password_hash="hash_de_prueba",
        nombres="Segunda",
        apellidos="Activa",
        estado="activa",
    )
    with pytest.raises(IntegrityError, match="uq_usuario_asistente_activa"):
        with db.begin_nested():
            db.add(segunda_activa_g1)
            db.flush()

    # Sin embargo, una asistente inactiva sí se puede agregar sin conflicto
    inactiva_g1 = crear_asistente_modelo(db, gerente1, "Inactiva1", estado="inactiva")
    assert inactiva_g1.estado == "inactiva"

    # Y gerente2 también puede tener su propia asistente activa sin interferir con gerente1
    asistente_activa_g2 = dos_gerentes.dos.asistente
    assert asistente_activa_g2.estado == "activa"
    assert asistente_activa_g2.gerente_id == gerente2.id


def test_ca02_asistente_activa_se_destaca_primero_en_la_lista(
    cliente: TestClient,
    dos_gerentes: DosGerentes,
    db: Session,
) -> None:
    """CA02: La cuenta activa se destaca apareciendo en la primera posición de la lista."""
    gerente = dos_gerentes.uno.gerente
    activa = dos_gerentes.uno.asistente

    # Crear asistentes inactivas con distintas antigüedades
    mas_reciente_inactiva = crear_asistente_modelo(
        db, gerente, "Reciente", estado="inactiva", horas_atras=2
    )
    mas_antigua_inactiva = crear_asistente_modelo(
        db, gerente, "Antigua", estado="inactiva", horas_atras=48
    )
    # Crear una eliminada que no debe aparecer
    crear_asistente_modelo(
        db,
        gerente,
        "Eliminada",
        estado="inactiva",
        horas_atras=5,
        eliminado_en=ahora_lima(),
    )

    # 1. Verificación a través del servicio SQL ORM consulta_lista
    cuentas_orm = db.scalars(consulta_lista(gerente)).all()
    assert [c.id for c in cuentas_orm] == [
        activa.id,
        mas_reciente_inactiva.id,
        mas_antigua_inactiva.id,
    ]

    # 2. Verificación a través del endpoint HTTP GET /api/v1/asistentes
    r = cliente.get(URL, headers=auth_headers(gerente))
    assert r.status_code == 200
    datos = r.json()
    assert datos["total"] == 3
    items = datos["items"]
    assert items[0]["id"] == str(activa.id)
    assert items[0]["estado"] == "activa"
    assert items[1]["id"] == str(mas_reciente_inactiva.id)
    assert items[1]["estado"] == "inactiva"
    assert items[2]["id"] == str(mas_antigua_inactiva.id)
    assert items[2]["estado"] == "inactiva"


def test_ca02_dos_activaciones_simultaneas_nunca_dejan_dos_asistentes_activas() -> None:
    """CA02: Dos solicitudes simultáneas de activación serializan y jamás dejan dos
    asistentes activas para el mismo gerente.
    """
    import concurrent.futures

    from sqlalchemy import select, text

    from app.core.database import SessionLocal
    from app.core.dependencias import Origen
    from app.services.asistentes import activar_asistente

    origen = Origen(dispositivo="pytest_concurrencia", ip=None)
    marca = uuid.uuid4().hex[:8]

    # Setup: 1 gerente y 2 asistentes inactivas
    with SessionLocal() as setup_db:
        gerente = Usuario(
            rol="gerente",
            username=f"g_conc_{marca}",
            password_hash="hash",
            nombres="Gerente",
            apellidos="Concurrente",
        )
        setup_db.add(gerente)
        setup_db.commit()
        setup_db.refresh(gerente)
        gerente_id = gerente.id

        asistente1 = Usuario(
            rol="asistente",
            gerente_id=gerente_id,
            username=f"a1_{marca}",
            password_hash="hash",
            nombres="Asistente Uno",
            apellidos="Pérez",
            estado="inactiva",
        )
        asistente2 = Usuario(
            rol="asistente",
            gerente_id=gerente_id,
            username=f"a2_{marca}",
            password_hash="hash",
            nombres="Asistente Dos",
            apellidos="López",
            estado="inactiva",
        )
        setup_db.add_all([asistente1, asistente2])
        setup_db.commit()
        setup_db.refresh(asistente1)
        setup_db.refresh(asistente2)
        id_1, id_2 = asistente1.id, asistente2.id

    try:

        def activar_en_hilo(asistente_id: uuid.UUID) -> str:
            with SessionLocal() as db_hilo:
                g = db_hilo.get_one(Usuario, gerente_id)
                resultado = activar_asistente(db_hilo, g, asistente_id, origen)
                db_hilo.commit()
                return resultado.activada.estado

        # Lanzar 2 activaciones simultáneas para asistentes distintas del mismo gerente
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            fut1 = executor.submit(activar_en_hilo, id_1)
            fut2 = executor.submit(activar_en_hilo, id_2)
            res1 = fut1.result(timeout=15)
            res2 = fut2.result(timeout=15)

        assert res1 == "activa"
        assert res2 == "activa"

        # Verificar en una nueva sesión que en la base de datos exactamente 1 asistente está activa
        with SessionLocal() as db_verif:
            activas = db_verif.scalars(
                select(Usuario).where(
                    Usuario.gerente_id == gerente_id,
                    Usuario.rol == "asistente",
                    Usuario.estado == "activa",
                    Usuario.eliminado_en.is_(None),
                )
            ).all()
            assert len(activas) == 1
            # La otra asistente debe haber quedado inactiva
            inactivas = db_verif.scalars(
                select(Usuario).where(
                    Usuario.gerente_id == gerente_id,
                    Usuario.rol == "asistente",
                    Usuario.estado == "inactiva",
                    Usuario.eliminado_en.is_(None),
                )
            ).all()
            assert len(inactivas) == 1
    finally:
        with SessionLocal() as db_clean:
            db_clean.execute(
                text("DELETE FROM activacion_cuenta WHERE realizada_por = :gid"),
                {"gid": gerente_id},
            )
            db_clean.execute(
                text("DELETE FROM auditoria WHERE gerente_id = :gid"),
                {"gid": gerente_id},
            )
            db_clean.execute(
                text("DELETE FROM usuario WHERE gerente_id = :gid"),
                {"gid": gerente_id},
            )
            db_clean.execute(
                text("DELETE FROM usuario WHERE id = :gid"),
                {"gid": gerente_id},
            )
            db_clean.commit()


def test_ca17_detalle_asistente_datos_estado_creacion_e_historial(
    cliente: TestClient,
    dos_gerentes: DosGerentes,
    db: Session,
) -> None:
    """CA17: El detalle muestra datos, estado, fecha de creación e historial de activaciones."""
    from app.services.asistentes import detalle_asistente

    gerente = dos_gerentes.uno.gerente
    gerente.nombres, gerente.apellidos = "Mariana", "Salazar"
    db.commit()

    # 1. Cuenta nueva sin cambios de estado: historial vacío
    nueva = crear_asistente_modelo(db, gerente, "SinHistorial", horas_atras=1)
    detalle_inicial = detalle_asistente(db, gerente, nueva.id)
    assert detalle_inicial.asistente.id == nueva.id
    assert detalle_inicial.historial == []

    # Verificación por API HTTP GET /api/v1/asistentes/{id}
    r_init = cliente.get(f"{URL}/{nueva.id}", headers=auth_headers(gerente))
    assert r_init.status_code == 200
    datos_init = r_init.json()
    assert datos_init["id"] == str(nueva.id)
    assert datos_init["nombres"] == "SinHistorial"
    assert datos_init["apellidos"] == "Gómez"
    assert datos_init["estado"] == "inactiva"
    assert datos_init["creado_en"] is not None
    assert datos_init["historial"] == []

    # 2. Registrar ciclo de activación y desactivación
    cliente.post(f"{URL}/{nueva.id}/activar", headers=auth_headers(gerente))
    cliente.post(f"{URL}/{nueva.id}/desactivar", headers=auth_headers(gerente))

    # Consultar detalle actualizado
    r_actualizado = cliente.get(f"{URL}/{nueva.id}", headers=auth_headers(gerente))
    assert r_actualizado.status_code == 200
    datos_act = r_actualizado.json()
    assert datos_act["id"] == str(nueva.id)
    assert datos_act["estado"] == "inactiva"

    historial = datos_act["historial"]
    assert len(historial) == 2
    # El historial se ordena del más reciente al más antiguo
    assert [ev["accion"] for ev in historial] == ["desactivada", "activada"]
    assert all(ev["realizada_por"] == "Mariana Salazar" for ev in historial)
    assert all("creado_en" in ev for ev in historial)


def test_ca17_aislamiento_multitenancy_ninguna_cuenta_ajena_visible(
    cliente: TestClient,
    dos_gerentes: DosGerentes,
    db: Session,
) -> None:
    """CA17 / Aislamiento: La consulta del gerente no cruza cuentas ajenas ni eliminadas."""
    gerente1 = dos_gerentes.uno.gerente
    asistente_g2 = dos_gerentes.dos.asistente

    # Crear una asistente eliminada para gerente1
    eliminada_g1 = crear_asistente_modelo(
        db,
        gerente1,
        "Eliminada",
        horas_atras=3,
        eliminado_en=ahora_lima(),
    )

    # 1. En la lista de gerente1, nunca aparece la asistente de gerente2 ni la eliminada
    r_lista = cliente.get(URL, headers=auth_headers(gerente1))
    assert r_lista.status_code == 200
    ids_en_lista = {item["id"] for item in r_lista.json()["items"]}
    assert str(asistente_g2.id) not in ids_en_lista
    assert str(eliminada_g1.id) not in ids_en_lista

    # 2. Consultar el detalle de una asistente ajena responde 404 NO_ENCONTRADO sin fugar datos
    r_ajena = cliente.get(f"{URL}/{asistente_g2.id}", headers=auth_headers(gerente1))
    assert r_ajena.status_code == 404
    assert r_ajena.json()["code"] == "NO_ENCONTRADO"

    # 3. Consultar el detalle de una eliminada o inexistente responde 404 NO_ENCONTRADO
    r_elim = cliente.get(f"{URL}/{eliminada_g1.id}", headers=auth_headers(gerente1))
    assert r_elim.status_code == 404
    assert r_elim.json()["code"] == "NO_ENCONTRADO"

    r_random = cliente.get(f"{URL}/{uuid.uuid4()}", headers=auth_headers(gerente1))
    assert r_random.status_code == 404
    assert r_random.json()["code"] == "NO_ENCONTRADO"


def test_ca17_autorizacion_asistente_y_anonimo_sin_acceso(
    cliente: TestClient,
    dos_gerentes: DosGerentes,
) -> None:
    """Autorización: Solo el rol gerente puede acceder a la lista y detalle de asistentes."""
    asistente = dos_gerentes.uno.asistente

    # Asistente intentando listar asistentes -> 403 SIN_PERMISO
    r_lista_asistente = cliente.get(URL, headers=auth_headers(asistente))
    assert r_lista_asistente.status_code == 403
    assert r_lista_asistente.json()["code"] == "SIN_PERMISO"

    # Asistente intentando consultar detalle -> 403 SIN_PERMISO
    r_detalle_asistente = cliente.get(f"{URL}/{asistente.id}", headers=auth_headers(asistente))
    assert r_detalle_asistente.status_code == 403
    assert r_detalle_asistente.json()["code"] == "SIN_PERMISO"

    # Usuario anónimo sin credenciales -> 401
    r_anon_lista = cliente.get(URL)
    assert r_anon_lista.status_code == 401

    r_anon_detalle = cliente.get(f"{URL}/{asistente.id}")
    assert r_anon_detalle.status_code == 401
