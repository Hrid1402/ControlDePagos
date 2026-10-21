import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.dependencias import Origen
from app.core.errores import ErrorApi
from app.core.eventos import Evento
from app.models import Auditoria, Deuda, SolicitudAprobacion, Usuario
from app.services.pagos import (
    AccionesPago,
    ResultadoInicio,
    acciones_de_pago,
    cancelar_inicio,
    iniciar_pago,
)
from app.services.saldo import consumo_mes_pen
from tests.conftest import DosGerentes, nueva_deuda, nueva_orden, nuevo_comprobante

Publicados = list[tuple[uuid.UUID, Evento]]

ORIGEN = Origen(dispositivo="pruebas", ip=None)
AHORA = datetime(2026, 10, 19, 17, 0, tzinfo=UTC)


def iniciada(db: Session, usuario: Usuario, gerente: Usuario, **opciones: str) -> Deuda:
    deuda = nueva_deuda(db, gerente, **opciones)
    inicio = iniciar_pago(db, usuario, deuda.id, origen=ORIGEN, ahora=AHORA)
    assert inicio.resultado == ResultadoInicio.INICIADO
    return deuda


def cancelar(db: Session, usuario: Usuario, deuda: Deuda, motivo: str | None = None) -> Deuda:
    return cancelar_inicio(db, usuario, deuda.id, motivo, origen=ORIGEN)


def error_de(accion: Callable[[], object]) -> ErrorApi:
    with pytest.raises(ErrorApi) as info:
        accion()
    return info.value


def cancelaciones(db: Session, deuda: Deuda) -> list[Auditoria]:
    return list(
        db.scalars(
            select(Auditoria).where(
                Auditoria.entidad_id == deuda.id, Auditoria.accion == "pago_inicio_cancelado"
            )
        )
    )


def nueva_asistente(db: Session, gerente: Usuario, anterior: Usuario) -> Usuario:
    anterior.estado = "inactiva"
    db.flush()
    asistente = Usuario(
        rol="asistente", gerente_id=gerente.id, username="asistente_nueva", password_hash="x"
    )
    db.add(asistente)
    db.flush()
    return asistente


def test_el_dueno_cancela_y_libera_la_reserva(
    db: Session, dos_gerentes: DosGerentes, publicados: Publicados
) -> None:
    equipo = dos_gerentes.uno
    deuda = iniciada(db, equipo.asistente, equipo.gerente)
    assert consumo_mes_pen(db, equipo.gerente.id, AHORA) == Decimal("100.00")

    cancelar(db, equipo.asistente, deuda)
    db.commit()

    assert deuda.estado == "pendiente"
    assert (deuda.pago_iniciado_por, deuda.pago_iniciado_en) == (None, None)
    assert consumo_mes_pen(db, equipo.gerente.id, AHORA) == Decimal(0)
    [registro] = cancelaciones(db, deuda)
    assert registro.detalle["iniciado_por"] == str(equipo.asistente.id)
    assert registro.detalle["motivo"] is None
    # Cancela el propio dueño: no hay a quién avisar.
    assert publicados == []


def test_con_abonos_vuelve_a_pagada_parcial(db: Session, dos_gerentes: DosGerentes) -> None:
    equipo = dos_gerentes.uno
    deuda = nueva_deuda(db, equipo.gerente, estado="pagada_parcial")
    nuevo_comprobante(db, deuda, equipo.asistente, "30.00")
    iniciar_pago(db, equipo.asistente, deuda.id, origen=ORIGEN)

    cancelar(db, equipo.asistente, deuda)

    assert deuda.estado == "pagada_parcial"


def test_el_gerente_resuelve_un_abandono_con_motivo_y_avisa_al_dueno(
    db: Session, dos_gerentes: DosGerentes, publicados: Publicados
) -> None:
    equipo = dos_gerentes.uno
    deuda = iniciada(db, equipo.asistente, equipo.gerente)

    cancelar(db, equipo.gerente, deuda, "  La asistente no fue al agente  ")
    db.commit()

    assert deuda.estado == "pendiente"
    [registro] = cancelaciones(db, deuda)
    assert registro.usuario_id == equipo.gerente.id
    assert registro.detalle["motivo"] == "La asistente no fue al agente"
    [(destinatario, evento)] = publicados
    assert destinatario == equipo.asistente.id
    assert evento.tipo == "pago_cancelado"
    assert evento.datos == {"deuda_id": str(deuda.id), "estado": "pendiente"}


@pytest.mark.parametrize("motivo", [None, "   "])
def test_el_gerente_debe_indicar_el_motivo(
    db: Session, dos_gerentes: DosGerentes, motivo: str | None
) -> None:
    equipo = dos_gerentes.uno
    deuda = iniciada(db, equipo.asistente, equipo.gerente)
    error = error_de(lambda: cancelar(db, equipo.gerente, deuda, motivo))
    assert (error.status_code, error.code, error.field) == (422, "VALIDACION", "motivo")
    assert deuda.estado == "en_proceso"


def test_otra_asistente_no_puede_cancelar_un_intento_ajeno(
    db: Session, dos_gerentes: DosGerentes
) -> None:
    equipo = dos_gerentes.uno
    deuda = iniciada(db, equipo.asistente, equipo.gerente)
    actual = nueva_asistente(db, equipo.gerente, equipo.asistente)

    error = error_de(lambda: cancelar(db, actual, deuda, "No la encuentro"))

    assert (error.status_code, error.code) == (403, "SIN_PERMISO")
    assert deuda.estado == "en_proceso"
    # El intento de la asistente anterior sigue reservado: el cambio no reinicia el consumo.
    assert consumo_mes_pen(db, equipo.gerente.id, AHORA) == Decimal("100.00")


@pytest.mark.parametrize("rol", ["asistente", "gerente"])
def test_un_pago_declarado_no_se_cancela(db: Session, dos_gerentes: DosGerentes, rol: str) -> None:
    equipo = dos_gerentes.uno
    deuda = iniciada(db, equipo.asistente, equipo.gerente)
    deuda.pago_realizado = True
    deuda.pago_realizado_en = datetime.now(UTC)
    db.flush()

    error = error_de(lambda: cancelar(db, getattr(equipo, rol), deuda, "Revisión"))

    assert (error.status_code, error.code) == (409, "PAGO_DECLARADO")
    assert deuda.estado == "en_proceso"


@pytest.mark.parametrize("estado", ["procesando", "en_revision", "por_confirmar"])
def test_un_comprobante_activo_impide_cancelar(
    db: Session, dos_gerentes: DosGerentes, estado: str
) -> None:
    equipo = dos_gerentes.uno
    deuda = iniciada(db, equipo.asistente, equipo.gerente)
    nuevo_comprobante(db, deuda, equipo.asistente, "100.00", estado=estado)

    error = error_de(lambda: cancelar(db, equipo.gerente, deuda, "Revisión"))

    assert (error.status_code, error.code) == (409, "COMPROBANTE_ACTIVO")


def test_sin_intento_en_curso_no_hay_nada_que_cancelar(
    db: Session, dos_gerentes: DosGerentes
) -> None:
    equipo = dos_gerentes.uno
    deuda = iniciada(db, equipo.asistente, equipo.gerente)
    cancelar(db, equipo.asistente, deuda)

    error = error_de(lambda: cancelar(db, equipo.asistente, deuda))

    assert (error.status_code, error.code) == (409, "SIN_INTENTO")
    assert len(cancelaciones(db, deuda)) == 1


def test_la_deuda_de_otro_gerente_no_existe(db: Session, dos_gerentes: DosGerentes) -> None:
    deuda = iniciada(db, dos_gerentes.uno.asistente, dos_gerentes.uno.gerente)
    error = error_de(lambda: cancelar(db, dos_gerentes.dos.gerente, deuda, "Ajena"))
    assert (error.status_code, error.code) == (404, "NO_ENCONTRADO")
    assert deuda.estado == "en_proceso"


def test_un_intento_abandonado_no_se_libera_por_tiempo(
    db: Session, dos_gerentes: DosGerentes
) -> None:
    equipo = dos_gerentes.uno
    deuda = nueva_deuda(db, equipo.gerente)
    hace_tres_dias = AHORA - timedelta(days=3)
    iniciar_pago(db, equipo.asistente, deuda.id, origen=ORIGEN, ahora=hace_tres_dias)

    # Ninguna consulta ni nuevo intento lo libera: sigue reservado y del mismo dueño.
    repetido = iniciar_pago(db, equipo.asistente, deuda.id, origen=ORIGEN)
    assert repetido.repetido
    assert (deuda.estado, deuda.pago_iniciado_en) == ("en_proceso", hace_tres_dias)
    assert consumo_mes_pen(db, equipo.gerente.id, AHORA) == Decimal("100.00")


def test_la_aprobacion_sirve_otra_vez_tras_cancelar(db: Session, dos_gerentes: DosGerentes) -> None:
    equipo = dos_gerentes.uno
    deuda = nueva_deuda(db, equipo.gerente, monto="40.00", moneda="USD")
    db.add(
        SolicitudAprobacion(
            deuda_id=deuda.id,
            asistente_id=equipo.asistente.id,
            monto=Decimal("40.00"),
            moneda="USD",
            estado="aprobada",
            resuelta_en=AHORA,
        )
    )
    db.flush()
    iniciar_pago(db, equipo.asistente, deuda.id, origen=ORIGEN)
    cancelar(db, equipo.asistente, deuda)

    inicio = iniciar_pago(db, equipo.asistente, deuda.id, origen=ORIGEN)

    assert inicio.resultado == ResultadoInicio.INICIADO


def test_la_orden_aceptada_sigue_aceptada_tras_cancelar(
    db: Session, dos_gerentes: DosGerentes
) -> None:
    equipo = dos_gerentes.uno
    deuda = iniciada(db, equipo.asistente, equipo.gerente)
    orden = nueva_orden(db, deuda, "aceptada", asistente=equipo.asistente)

    cancelar(db, equipo.asistente, deuda)

    assert orden.estado == "aceptada"


def test_acciones_de_pago_siguen_las_reglas_del_servicio(
    db: Session, dos_gerentes: DosGerentes
) -> None:
    equipo = dos_gerentes.uno
    pendiente = nueva_deuda(db, equipo.gerente)
    assert acciones_de_pago(db, pendiente, equipo.asistente) == AccionesPago(True, False)
    assert acciones_de_pago(db, pendiente, dos_gerentes.dos.gerente) == AccionesPago(False, False)

    deuda = iniciada(db, equipo.asistente, equipo.gerente)
    assert acciones_de_pago(db, deuda, equipo.asistente) == AccionesPago(False, True)
    assert acciones_de_pago(db, deuda, equipo.gerente) == AccionesPago(False, True)
    actual = nueva_asistente(db, equipo.gerente, equipo.asistente)
    assert acciones_de_pago(db, deuda, actual) == AccionesPago(False, False)

    deuda.pago_realizado = True
    deuda.pago_realizado_en = datetime.now(UTC)
    db.flush()
    assert acciones_de_pago(db, deuda, equipo.gerente) == AccionesPago(False, False)
