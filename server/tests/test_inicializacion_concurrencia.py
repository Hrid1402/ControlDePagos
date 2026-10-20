"""Inicializaciones simultáneas del gerente con transacciones reales (TASK-27).

Como en test_cuenta_concurrencia.py, estas pruebas no usan el fixture db: cada ejecución abre
su propia sesión y confirma con commit, como dos procesos del comando. Cada prueba usa un
username único y borra lo creado en un finally. Cada transacción fija un lock_timeout y cada
hilo un tiempo máximo, para que una espera que no termina haga fallar la prueba.
"""

import threading
import uuid
from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import Select, func, select, text
from sqlalchemy.orm import Session

from app.core.database import SessionLocal, engine
from app.models import Auditoria, Categoria, Usuario
from app.schemas.inicializacion import DatosGerente
from app.services.auditoria import Accion
from app.services.inicializacion import (
    CATEGORIAS_PRECARGADAS,
    ConflictoInicializacion,
    Inicializacion,
    crear_gerente,
    inicializar_gerente,
    precargar_categorias,
)
from tests.test_inicializacion import CONTRASENA, ORIGEN

SEGUNDOS_MAXIMOS = 15
ESPERA_BLOQUEO = "10s"
HILOS = 4

# La auditoría se borra con SQL directo: el ORM la protege de borrados.
# historial_contrasena cae con el usuario (CASCADE).
BORRADOS = """
DELETE FROM auditoria WHERE gerente_id IN (SELECT id FROM usuario WHERE username = ANY(:nombres));
DELETE FROM categoria WHERE gerente_id IN (SELECT id FROM usuario WHERE username = ANY(:nombres));
DELETE FROM usuario WHERE username = ANY(:nombres);
"""


def sesion() -> Session:
    db = SessionLocal()
    db.execute(text(f"SET LOCAL lock_timeout = '{ESPERA_BLOQUEO}'"))
    return db


@pytest.fixture
def username() -> Iterator[str]:
    nombre = f"g_{uuid.uuid4().hex[:12]}"
    try:
        yield nombre
    finally:
        with engine.begin() as conexion:
            for sentencia in filter(str.strip, BORRADOS.split(";")):
                conexion.execute(text(sentencia), {"nombres": [nombre]})


def inicializar(username: str) -> Inicializacion:
    with sesion() as db:
        return inicializar_gerente(db, DatosGerente(username=username), CONTRASENA, ORIGEN)


def en_paralelo(tarea: Callable[[], Inicializacion], hilos: int = HILOS) -> list[Inicializacion]:
    barrera = threading.Barrier(hilos, timeout=SEGUNDOS_MAXIMOS)

    def esperar_y_ejecutar() -> Inicializacion:
        barrera.wait()
        return tarea()

    with ThreadPoolExecutor(hilos) as ejecutor:
        futuros = [ejecutor.submit(esperar_y_ejecutar) for _ in range(hilos)]
        return [f.result(timeout=SEGUNDOS_MAXIMOS) for f in futuros]


def contar(db: Session, consulta: Select[tuple[uuid.UUID]]) -> int:
    return db.scalar(select(func.count()).select_from(consulta.subquery())) or 0


def estado_final(username: str) -> tuple[int, int, int, int]:
    """Gerentes con el username, sus categorías y sus eventos de creación de cuenta y categoría."""
    with SessionLocal() as db:
        ids = list(db.scalars(select(Usuario.id).where(Usuario.username == username)))
        eventos = select(Auditoria.id).where(Auditoria.gerente_id.in_(ids))
        return (
            len(ids),
            contar(db, select(Categoria.id).where(Categoria.gerente_id.in_(ids))),
            contar(db, eventos.where(Auditoria.accion == Accion.CUENTA_CREADA)),
            contar(db, eventos.where(Auditoria.accion == Accion.CATEGORIA_CREADA)),
        )


ESPERADO = (1, len(CATEGORIAS_PRECARGADAS), 1, len(CATEGORIAS_PRECARGADAS))


def test_ejecuciones_simultaneas_con_el_mismo_username_crean_un_solo_gerente(
    username: str,
) -> None:
    resultados = en_paralelo(lambda: inicializar(username))

    assert sum(r.creado for r in resultados) == 1
    assert len({r.gerente.id for r in resultados}) == 1
    assert sum(len(r.categorias.creadas) for r in resultados) == len(CATEGORIAS_PRECARGADAS)
    assert estado_final(username) == ESPERADO


def test_la_ejecucion_que_espera_a_otra_sin_confirmar_encuentra_su_gerente(
    username: str,
) -> None:
    """Determinista: la primera inserta y no confirma; la segunda queda esperando en su INSERT
    y, al confirmarse la primera, sigue como si el gerente ya existiera."""
    primera = sesion()
    try:
        gerente = crear_gerente(primera, DatosGerente(username=username), CONTRASENA, ORIGEN)
        assert gerente is not None
        with ThreadPoolExecutor(1) as ejecutor:
            segunda = ejecutor.submit(inicializar, username)
            # La segunda no puede terminar mientras la primera no confirme.
            with pytest.raises(TimeoutError):
                segunda.result(timeout=1)
            precargar_categorias(primera, gerente, ORIGEN)
            primera.commit()
            resultado = segunda.result(timeout=SEGUNDOS_MAXIMOS)
    finally:
        primera.close()

    assert not resultado.creado
    assert resultado.gerente.id == gerente.id
    assert resultado.categorias.creadas == []
    assert estado_final(username) == ESPERADO


def test_completar_en_paralelo_las_precargadas_de_un_gerente_no_las_duplica(
    username: str,
) -> None:
    with sesion() as db:
        gerente = crear_gerente(db, DatosGerente(username=username), CONTRASENA, ORIGEN)
        assert gerente is not None
        db.commit()

    resultados = en_paralelo(lambda: inicializar(username))

    assert not any(r.creado for r in resultados)
    assert sum(len(r.categorias.creadas) for r in resultados) == len(CATEGORIAS_PRECARGADAS)
    assert estado_final(username) == ESPERADO


def test_dos_gerentes_simultaneos_con_el_mismo_correo_dejan_solo_uno(username: str) -> None:
    """La segunda no ve el correo de la primera, que aún no confirma, y choca con
    uq_usuario_correo al insertar: es conflicto y el mensaje no trae el hash."""
    otro = f"{username}_b"
    correo = f"{username}@ejemplo.pe"
    primera = sesion()
    try:
        crear_gerente(primera, DatosGerente(username=username, correo=correo), CONTRASENA, ORIGEN)

        def segunda() -> Inicializacion:
            with sesion() as db:
                datos = DatosGerente(username=otro, correo=correo)
                return inicializar_gerente(db, datos, CONTRASENA, ORIGEN)

        with ThreadPoolExecutor(1) as ejecutor:
            futuro = ejecutor.submit(segunda)
            with pytest.raises(TimeoutError):
                futuro.result(timeout=1)
            primera.commit()
            with pytest.raises(ConflictoInicializacion, match="correo") as error:
                futuro.result(timeout=SEGUNDOS_MAXIMOS)
    finally:
        primera.close()
        with engine.begin() as conexion:
            for sentencia in filter(str.strip, BORRADOS.split(";")):
                conexion.execute(text(sentencia), {"nombres": [otro]})

    assert "$2b$" not in str(error.value)
    assert error.value.__cause__ is None
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).where(Usuario.correo == correo)) == 1
        assert db.scalar(select(func.count()).where(Usuario.username == otro)) == 0
