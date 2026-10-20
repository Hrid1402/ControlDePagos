"""Registros simultáneos del mismo servicio con transacciones reales (H10 CA03, TASK-33).

Como en test_cuenta_concurrencia.py, estas pruebas no usan el fixture db: cada registro abre su
propia sesión y confirma con commit, como dos solicitudes del server. El gerente y su categoría
se crean confirmados y se borran con todo lo suyo en un finally, aunque la prueba falle. Cada
transacción fija un lock_timeout y cada hilo un tiempo máximo, para que una espera que no
termina haga fallar la prueba en lugar de colgar la suite.
"""

import threading
import uuid
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.core.database import SessionLocal, engine
from app.core.dependencias import Origen
from app.core.errores import ErrorApi
from app.models import Auditoria, Categoria, Servicio, Usuario
from app.schemas.servicios import ServicioEntrada
from app.services import servicios
from app.services.auditoria import Accion
from app.services.servicios import crear_servicio

ORIGEN = Origen(dispositivo="pruebas", ip=None)
SEGUNDOS_MAXIMOS = 15
ESPERA_BLOQUEO = "10s"
HILOS = 2

# La auditoría se borra con SQL directo: el ORM la protege de borrados.
BORRADOS = """
DELETE FROM auditoria WHERE gerente_id = :id;
DELETE FROM servicio WHERE gerente_id = :id;
DELETE FROM categoria WHERE gerente_id = :id;
DELETE FROM usuario WHERE id = :id;
"""


@dataclass(frozen=True)
class Datos:
    gerente_id: uuid.UUID
    categoria_id: uuid.UUID


def sesion() -> Session:
    db = SessionLocal()
    db.execute(text(f"SET LOCAL lock_timeout = '{ESPERA_BLOQUEO}'"))
    return db


@pytest.fixture
def gerente() -> Iterator[Datos]:
    with SessionLocal() as db:
        usuario = Usuario(rol="gerente", username=f"g_{uuid.uuid4().hex[:12]}", password_hash="x")
        db.add(usuario)
        db.flush()
        categoria = Categoria(gerente_id=usuario.id, nombre="Luz", tipo="servicio_variable")
        db.add(categoria)
        db.commit()
        datos = Datos(usuario.id, categoria.id)
    try:
        yield datos
    finally:
        with engine.begin() as conexion:
            for sentencia in filter(str.strip, BORRADOS.split(";")):
                conexion.execute(text(sentencia), {"id": datos.gerente_id})
            quedan = conexion.scalar(
                text("SELECT count(*) FROM usuario WHERE id = :id"), {"id": datos.gerente_id}
            )
        assert quedan == 0


def registrar(datos: Datos, entrada: ServicioEntrada) -> uuid.UUID | ErrorApi:
    with sesion() as db:
        usuario = db.get_one(Usuario, datos.gerente_id)
        try:
            fila = crear_servicio(db, usuario, datos.gerente_id, entrada, ORIGEN)
        except ErrorApi as error:
            db.rollback()
            return error
        db.commit()
        return fila.servicio.id


def test_dos_registros_simultaneos_de_la_misma_empresa_y_codigo_dejan_uno(
    gerente: Datos, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Los dos pasan la consulta previa, como si llegaran al mismo tiempo: decide el índice. El
    # segundo espera el commit del primero y recibe el mismo 409.
    monkeypatch.setattr(servicios, "existe_duplicado", lambda *_, **__: False)
    # Escritos distintos que normalizan igual.
    entradas = [
        ServicioEntrada(
            categoria_id=gerente.categoria_id,
            empresa_nombre=nombre,
            codigo_suministro=codigo,
            lugar_pago="agente_bcp",
        )
        for nombre, codigo in (("Luz Norte", "123 456"), ("LUZ  NORTE", "123456"))
    ]
    barrera = threading.Barrier(HILOS, timeout=SEGUNDOS_MAXIMOS)

    def esperar_y_registrar(entrada: ServicioEntrada) -> uuid.UUID | ErrorApi:
        barrera.wait()
        return registrar(gerente, entrada)

    with ThreadPoolExecutor(HILOS) as ejecutor:
        futuros = [ejecutor.submit(esperar_y_registrar, e) for e in entradas]
        resultados = [f.result(timeout=SEGUNDOS_MAXIMOS) for f in futuros]

    creados = [r for r in resultados if isinstance(r, uuid.UUID)]
    errores = [r for r in resultados if isinstance(r, ErrorApi)]
    assert len(creados) == 1
    assert [(e.status_code, e.code, e.field) for e in errores] == [
        (409, "DUPLICADO", "codigo_suministro")
    ]
    with SessionLocal() as db:
        guardados = list(
            db.scalars(select(Servicio).where(Servicio.gerente_id == gerente.gerente_id))
        )
        eventos = db.scalar(
            select(func.count())
            .select_from(Auditoria)
            .where(
                Auditoria.gerente_id == gerente.gerente_id,
                Auditoria.accion == Accion.SERVICIO_CREADO.value,
            )
        )
    assert [(s.id, s.codigo_suministro) for s in guardados] == [(creados[0], "123456")]
    assert eventos == 1
