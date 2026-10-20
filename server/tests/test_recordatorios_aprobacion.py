"""Recordatorios de solicitudes pendientes (H05 CA09, TASK-24).

Un aviso al gerente por cada turno de 2 horas sin respuesta y, el día en que la deuda vence, uno
urgente de inmediato. El job es idempotente, no repite turnos atrasados y se detiene al resolver.
"""

from collections.abc import Iterator
from datetime import date, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.dependencias import Origen
from app.core.tiempo import zona_horaria
from app.models import Notificacion, SolicitudAprobacion, Usuario
from app.services.limites import fijar_limite, recordar_pendientes, resolver_solicitud
from app.services.pagos import iniciar_pago
from app.workers import aprobaciones as modulo
from app.workers import base
from tests.conftest import DosGerentes, Equipo, nueva_deuda

ORIGEN = Origen(dispositivo="pruebas", ip=None)
LIMA = zona_horaria()
PEDIDA = datetime(2026, 10, 20, 9, 0, tzinfo=LIMA)


def pedir(db: Session, equipo: Equipo, vence: date = date(2026, 10, 25)) -> SolicitudAprobacion:
    fijar_limite(db, equipo.gerente.id, por_pago=Decimal("100.00"))
    deuda = nueva_deuda(db, equipo.gerente, monto="250.00", fecha_vencimiento=vence)
    solicitud = iniciar_pago(db, equipo.asistente, deuda.id, origen=ORIGEN, ahora=PEDIDA).solicitud
    assert solicitud is not None
    solicitud.creado_en = PEDIDA
    db.flush()
    return solicitud


def recordatorios(db: Session, gerente: Usuario) -> list[Notificacion]:
    return list(
        db.scalars(
            select(Notificacion)
            .where(
                Notificacion.usuario_id == gerente.id,
                Notificacion.titulo == "Recordatorio de aprobación",
            )
            .order_by(Notificacion.id)
        )
    )


def test_recuerda_cada_dos_horas_sin_repetir_el_turno(
    db: Session, dos_gerentes: DosGerentes
) -> None:
    gerente = dos_gerentes.uno.gerente
    solicitud = pedir(db, dos_gerentes.uno)

    assert recordar_pendientes(db, PEDIDA + timedelta(hours=1, minutes=59)) == 0
    assert recordar_pendientes(db, PEDIDA + timedelta(hours=2)) == 1
    # El mismo turno otra vez, o el job repetido, no avisa de nuevo.
    assert recordar_pendientes(db, PEDIDA + timedelta(hours=3)) == 0
    assert recordar_pendientes(db, PEDIDA + timedelta(hours=4, minutes=5)) == 1

    avisos = recordatorios(db, gerente)
    assert [a.clave_evento for a in avisos] == [
        f"recordatorio_aprobacion:{solicitud.id}:1",
        f"recordatorio_aprobacion:{solicitud.id}:2",
    ]
    assert not any(a.urgente for a in avisos)
    assert "espera tu respuesta al pago de PEN 250.00" in avisos[0].mensaje
    assert solicitud.recordatorios_enviados == 2


def test_tras_una_parada_solo_avisa_el_turno_actual(db: Session, dos_gerentes: DosGerentes) -> None:
    solicitud = pedir(db, dos_gerentes.uno)

    assert recordar_pendientes(db, PEDIDA + timedelta(hours=9)) == 1
    assert recordar_pendientes(db, PEDIDA + timedelta(hours=9, minutes=15)) == 0
    assert solicitud.recordatorios_enviados == 4
    assert len(recordatorios(db, dos_gerentes.uno.gerente)) == 1


def test_el_dia_que_vence_avisa_de_inmediato_y_urgente(
    db: Session, dos_gerentes: DosGerentes
) -> None:
    gerente = dos_gerentes.uno.gerente
    solicitud = pedir(db, dos_gerentes.uno, vence=date(2026, 10, 21))
    # 00:30 del día que vence: aún no se cumple otro turno, pero se avisa ya.
    madrugada = datetime(2026, 10, 21, 0, 30, tzinfo=LIMA)

    assert recordar_pendientes(db, madrugada) == 1
    assert recordar_pendientes(db, madrugada + timedelta(minutes=15)) == 0
    # Cuenta como el turno en curso: el siguiente llega con el turno que sigue.
    assert recordar_pendientes(db, datetime(2026, 10, 21, 1, 0, tzinfo=LIMA)) == 1

    urgente, siguiente = recordatorios(db, gerente)
    assert urgente.clave_evento == f"aprobacion_vence_hoy:{solicitud.id}:2026-10-21"
    assert urgente.urgente and siguiente.urgente
    assert "vence hoy" in urgente.mensaje


def test_al_resolverla_deja_de_recordarse(db: Session, dos_gerentes: DosGerentes) -> None:
    equipo = dos_gerentes.uno
    solicitud = pedir(db, equipo)
    resolver_solicitud(db, equipo.gerente, solicitud.id, "rechazada", origen=ORIGEN)

    assert recordar_pendientes(db, PEDIDA + timedelta(hours=6)) == 0
    assert recordatorios(db, equipo.gerente) == []


@pytest.fixture
def sesion_de_prueba(db: Session, monkeypatch: pytest.MonkeyPatch) -> Iterator[Session]:
    """El job usa la sesión de la prueba: confirma sobre su savepoint y no deja datos."""

    class Fabrica:
        def __enter__(self) -> Session:
            return db

        def __exit__(self, *_: object) -> None:
            return None

    monkeypatch.setattr(base, "fabrica_sesiones", Fabrica)
    monkeypatch.setattr(modulo, "BLOQUEO_APROBACIONES", f"pruebas-aprobaciones-{id(db)}")
    yield db


def test_la_tarea_programada_envia_los_recordatorios(
    sesion_de_prueba: Session, dos_gerentes: DosGerentes, monkeypatch: pytest.MonkeyPatch
) -> None:
    pedir(sesion_de_prueba, dos_gerentes.uno)
    monkeypatch.setattr(modulo, "ahora_lima", lambda: PEDIDA + timedelta(hours=2))

    assert modulo.recordar_aprobaciones.apply().get() == 1
    assert modulo.recordar_aprobaciones.apply().get() == 0


def test_con_otra_ejecucion_en_curso_la_tarea_no_hace_nada(
    sesion_de_prueba: Session, dos_gerentes: DosGerentes
) -> None:
    pedir(sesion_de_prueba, dos_gerentes.uno)
    with base.un_solo_a_la_vez(modulo.BLOQUEO_APROBACIONES) as tomado:
        assert tomado
        assert modulo.recordar_aprobaciones.apply().get() is None
