"""Registros simultáneos de la misma deuda con transacciones reales (H11 CA03, TASK-38).

Como en test_servicios_concurrencia.py, estas pruebas no usan el fixture db: cada solicitud abre
su propia sesión y confirma con commit. El equipo, su categoría y su servicio se crean
confirmados y se borran con todo lo suyo en un finally, aunque la prueba falle. Cada transacción
fija un lock_timeout y cada hilo un tiempo máximo, para que una espera que no termina haga fallar
la prueba en lugar de colgar la suite.
"""

import threading
import time
import uuid
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.core.database import SessionLocal, engine
from app.core.dependencias import Origen
from app.core.errores import ErrorApi
from app.core.eventos import Evento
from app.models import Auditoria, Categoria, Deuda, Servicio, Usuario
from app.schemas.deudas import DeudaEntrada
from app.services import deudas
from app.services.auditoria import Accion
from app.services.deudas import registrar_deuda
from app.services.servicios import Baja, dar_de_baja

ORIGEN = Origen(dispositivo="pruebas", ip=None)
SEGUNDOS_MAXIMOS = 15
ESPERA_BLOQUEO = "10s"
HILOS = 2

# La auditoría se borra con SQL directo: el ORM la protege de borrados. La asistente antes que
# su gerente, por fk_usuario_gerente_id.
BORRADOS = """
DELETE FROM notificacion WHERE usuario_id IN (SELECT id FROM usuario WHERE id = :id
  OR gerente_id = :id);
DELETE FROM auditoria WHERE gerente_id = :id;
DELETE FROM deuda WHERE gerente_id = :id;
DELETE FROM servicio WHERE gerente_id = :id;
DELETE FROM categoria WHERE gerente_id = :id;
DELETE FROM usuario WHERE gerente_id = :id;
DELETE FROM usuario WHERE id = :id;
"""


@dataclass(frozen=True)
class Datos:
    gerente_id: uuid.UUID
    asistente_id: uuid.UUID
    servicio_id: uuid.UUID


def sesion() -> Session:
    db = SessionLocal()
    db.execute(text(f"SET LOCAL lock_timeout = '{ESPERA_BLOQUEO}'"))
    return db


@pytest.fixture
def equipo(publicados: list[tuple[uuid.UUID, Evento]]) -> Iterator[Datos]:
    # publicados evita enviar a Redis el aviso al gerente cuando registra la asistente.
    marca = uuid.uuid4().hex[:12]
    with SessionLocal() as db:
        gerente = Usuario(rol="gerente", username=f"g_{marca}", password_hash="x")
        db.add(gerente)
        db.flush()
        asistente = Usuario(
            rol="asistente", gerente_id=gerente.id, username=f"a_{marca}", password_hash="x"
        )
        categoria = Categoria(gerente_id=gerente.id, nombre="Luz", tipo="servicio_variable")
        db.add_all([asistente, categoria])
        db.flush()
        servicio = Servicio(
            gerente_id=gerente.id,
            categoria_id=categoria.id,
            empresa_nombre="Electro Norte",
            codigo_suministro=marca.upper(),
        )
        db.add(servicio)
        db.commit()
        datos = Datos(gerente.id, asistente.id, servicio.id)
    try:
        yield datos
    finally:
        with engine.begin() as conexion:
            for sentencia in filter(str.strip, BORRADOS.split(";")):
                conexion.execute(text(sentencia), {"id": datos.gerente_id})
            quedan = conexion.scalar(
                text("SELECT count(*) FROM usuario WHERE id = :id OR gerente_id = :id"),
                {"id": datos.gerente_id},
            )
        assert quedan == 0


def entrada(datos: Datos, monto: str = "150.00") -> DeudaEntrada:
    return DeudaEntrada(
        servicio_id=datos.servicio_id, monto=Decimal(monto), fecha_vencimiento=date(2026, 10, 25)
    )


def registrar(datos: Datos, usuario_id: uuid.UUID, deuda: DeudaEntrada) -> uuid.UUID | ErrorApi:
    with sesion() as db:
        usuario = db.get_one(Usuario, usuario_id)
        try:
            registro = registrar_deuda(db, usuario, datos.gerente_id, deuda, ORIGEN)
        except ErrorApi as error:
            db.rollback()
            return error
        db.commit()
        return registro.deuda.id


def guardadas(datos: Datos) -> list[Deuda]:
    with SessionLocal() as db:
        return list(db.scalars(select(Deuda).where(Deuda.servicio_id == datos.servicio_id)))


def eventos_creada(datos: Datos) -> int:
    with SessionLocal() as db:
        return (
            db.scalar(
                select(func.count())
                .select_from(Auditoria)
                .where(
                    Auditoria.gerente_id == datos.gerente_id,
                    Auditoria.accion == Accion.DEUDA_CREADA.value,
                )
            )
            or 0
        )


def esperar_bloqueo_del_servicio() -> None:
    """Espera a que un registro quede esperando el bloqueo del servicio. Cada consulta abre su
    propia conexión: pg_stat_activity no cambia dentro de una misma transacción."""
    limite = time.monotonic() + SEGUNDOS_MAXIMOS
    while time.monotonic() < limite:
        with engine.connect() as conexion:
            esperando = conexion.scalar(
                text(
                    "SELECT count(*) FROM pg_stat_activity WHERE wait_event_type = 'Lock' "
                    "AND query ILIKE '%FROM servicio%FOR UPDATE%'"
                )
            )
        if esperando:
            return
        time.sleep(0.05)
    raise AssertionError("El registro no llegó a esperar el bloqueo del servicio.")


def test_dos_registros_simultaneos_del_mismo_periodo_dejan_una_deuda(equipo: Datos) -> None:
    # Gerente y asistente registran a la vez: se turnan en el bloqueo del servicio y el segundo
    # recibe el 409 con la deuda del primero.
    barrera = threading.Barrier(HILOS, timeout=SEGUNDOS_MAXIMOS)

    def esperar_y_registrar(usuario_id: uuid.UUID, monto: str) -> uuid.UUID | ErrorApi:
        barrera.wait()
        return registrar(equipo, usuario_id, entrada(equipo, monto))

    with ThreadPoolExecutor(HILOS) as ejecutor:
        futuros = [
            ejecutor.submit(esperar_y_registrar, usuario_id, monto)
            for usuario_id, monto in (
                (equipo.gerente_id, "150.00"),
                (equipo.asistente_id, "151.00"),
            )
        ]
        resultados = [f.result(timeout=SEGUNDOS_MAXIMOS) for f in futuros]

    creadas = [r for r in resultados if isinstance(r, uuid.UUID)]
    errores = [r for r in resultados if isinstance(r, ErrorApi)]
    assert len(creadas) == 1
    assert [(e.status_code, e.code, e.field) for e in errores] == [(409, "DUPLICADO", "periodo")]
    assert errores[0].datos["deuda_existente"]["id"] == str(creadas[0])
    assert [d.id for d in guardadas(equipo)] == creadas
    assert eventos_creada(equipo) == 1


def test_una_insercion_de_otro_proceso_responde_el_mismo_409_desde_el_indice(
    equipo: Datos, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Otro proceso, como la generación de recurrentes, inserta la deuda del periodo sin bloquear
    # el servicio y aún no confirma. Su llave foránea toma FOR KEY SHARE sobre el servicio, así
    # que el registro espera su commit. La consulta previa se omite para llegar al respaldo: el
    # índice rechaza la inserción y se responde el mismo 409 con la deuda del otro proceso.
    real = deudas.deuda_activa_del_periodo
    consultas: list[uuid.UUID | None] = []

    def sin_consulta_previa(db: Session, servicio_id: uuid.UUID, periodo: date) -> Deuda | None:
        encontrada = real(db, servicio_id, periodo) if consultas else None
        consultas.append(encontrada.id if encontrada else None)
        return encontrada

    monkeypatch.setattr(deudas, "deuda_activa_del_periodo", sin_consulta_previa)
    with SessionLocal() as otra:
        recurrente = Deuda(
            gerente_id=equipo.gerente_id,
            servicio_id=equipo.servicio_id,
            periodo=date(2026, 10, 1),
            monto=None,
            estado="esperando_recibo",
            origen="recurrente",
            fecha_vencimiento=date(2026, 10, 25),
        )
        otra.add(recurrente)
        otra.flush()
        recurrente_id = recurrente.id

        with ThreadPoolExecutor(1) as ejecutor:
            futuro = ejecutor.submit(registrar, equipo, equipo.asistente_id, entrada(equipo))
            esperar_bloqueo_del_servicio()
            otra.commit()
            resultado = futuro.result(timeout=SEGUNDOS_MAXIMOS)

    assert isinstance(resultado, ErrorApi)
    assert (resultado.status_code, resultado.code) == (409, "DUPLICADO")
    # La segunda consulta es la del respaldo, después del rechazo del índice.
    assert consultas == [None, recurrente_id]
    referencia = resultado.datos["deuda_existente"]
    assert (referencia["id"], referencia["estado"], referencia["monto"]) == (
        str(recurrente_id),
        "esperando_recibo",
        None,
    )
    assert [d.id for d in guardadas(equipo)] == [recurrente_id]
    assert eventos_creada(equipo) == 0


def test_un_registro_y_una_baja_simultaneos_no_dejan_deudas_despues_de_la_baja(
    equipo: Datos,
) -> None:
    # Se turnan en el bloqueo del servicio: o la baja llega primero y el registro recibe 409, o
    # el registro llega primero y la baja cuenta su deuda como pendiente. Nunca queda una deuda
    # que la baja no vio.
    barrera = threading.Barrier(HILOS, timeout=SEGUNDOS_MAXIMOS)

    def baja() -> Baja:
        with sesion() as db:
            gerente = db.get_one(Usuario, equipo.gerente_id)
            barrera.wait()
            resultado = dar_de_baja(db, gerente, equipo.servicio_id, ORIGEN)
            db.commit()
            return resultado

    def registro() -> uuid.UUID | ErrorApi:
        barrera.wait()
        return registrar(equipo, equipo.asistente_id, entrada(equipo))

    with ThreadPoolExecutor(HILOS) as ejecutor:
        futuro_baja, futuro_registro = ejecutor.submit(baja), ejecutor.submit(registro)
        resultado_baja = futuro_baja.result(timeout=SEGUNDOS_MAXIMOS)
        resultado_registro = futuro_registro.result(timeout=SEGUNDOS_MAXIMOS)

    deudas = guardadas(equipo)
    assert len(deudas) == resultado_baja.deudas_pendientes
    if isinstance(resultado_registro, ErrorApi):
        assert (resultado_registro.status_code, resultado_registro.code) == (
            409,
            "SERVICIO_DE_BAJA",
        )
        assert deudas == []
    else:
        assert [d.id for d in deudas] == [resultado_registro]
