from collections.abc import Callable
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.dependencias import Origen
from app.core.errores import ErrorApi
from app.models import (
    Auditoria,
    Deuda,
    Limite,
    Notificacion,
    OrdenPago,
    SolicitudAprobacion,
    Usuario,
)
from app.services.pagos import (
    AutorizacionOrden,
    InicioPago,
    ResultadoInicio,
    acciones_de_pago,
    iniciar_pago,
)
from app.services.saldo import consumo_mes_pen
from tests.conftest import DosGerentes, Equipo, nueva_deuda, nuevo_comprobante

ORIGEN = Origen(dispositivo="pruebas", ip=None)
AHORA = datetime(2026, 10, 19, 17, 0, tzinfo=UTC)  # 19/10 12:00 en Lima


def iniciar(db: Session, usuario: Usuario, deuda: Deuda, **opciones: Any) -> InicioPago:
    return iniciar_pago(db, usuario, deuda.id, origen=ORIGEN, ahora=AHORA, **opciones)


def error_de(accion: Callable[[], object]) -> ErrorApi:
    with pytest.raises(ErrorApi) as info:
        accion()
    return info.value


def fijar_limite(
    db: Session, gerente: Usuario, por_pago: str | None = None, mensual: str | None = None
) -> None:
    db.add(
        Limite(
            gerente_id=gerente.id,
            por_pago=Decimal(por_pago) if por_pago else None,
            mensual=Decimal(mensual) if mensual else None,
        )
    )
    db.flush()


def auditorias(db: Session, deuda: Deuda, accion: str) -> list[Auditoria]:
    return list(
        db.scalars(
            select(Auditoria).where(Auditoria.entidad_id == deuda.id, Auditoria.accion == accion)
        )
    )


def notificaciones_de(db: Session, usuario: Usuario) -> list[Notificacion]:
    return list(db.scalars(select(Notificacion).where(Notificacion.usuario_id == usuario.id)))


def aprobar(db: Session, equipo: Equipo, deuda: Deuda, monto: str, moneda: str) -> None:
    db.add(
        SolicitudAprobacion(
            deuda_id=deuda.id,
            asistente_id=equipo.asistente.id,
            monto=Decimal(monto),
            moneda=moneda,
            estado="aprobada",
            resuelta_por=equipo.gerente.id,
            resuelta_en=AHORA,
        )
    )
    db.flush()


def test_asistente_dentro_del_limite_inicia_y_reserva(
    db: Session, dos_gerentes: DosGerentes
) -> None:
    equipo = dos_gerentes.uno
    fijar_limite(db, equipo.gerente, mensual="500.00")
    deuda = nueva_deuda(db, equipo.gerente, monto="100.00")

    inicio = iniciar(db, equipo.asistente, deuda)

    assert (inicio.resultado, inicio.saldo, inicio.repetido) == (
        ResultadoInicio.INICIADO,
        Decimal("100.00"),
        False,
    )
    assert deuda.estado == "en_proceso"
    assert deuda.pago_iniciado_por == equipo.asistente.id
    assert deuda.pago_iniciado_en == AHORA
    assert consumo_mes_pen(db, equipo.gerente.id, AHORA) == Decimal("100.00")
    [registro] = auditorias(db, deuda, "pago_iniciado")
    assert registro.detalle["autorizacion"] == "limite"
    assert registro.detalle["estado_anterior"] == "pendiente"


def test_sin_limite_configurado_no_hay_tope_en_soles(
    db: Session, dos_gerentes: DosGerentes
) -> None:
    deuda = nueva_deuda(db, dos_gerentes.uno.gerente, monto="99999.00")
    assert iniciar(db, dos_gerentes.uno.asistente, deuda).resultado == ResultadoInicio.INICIADO


def test_superar_el_limite_por_pago_pide_aprobacion(db: Session, dos_gerentes: DosGerentes) -> None:
    equipo = dos_gerentes.uno
    fijar_limite(db, equipo.gerente, por_pago="50.00")
    deuda = nueva_deuda(db, equipo.gerente, monto="80.00")

    inicio = iniciar(db, equipo.asistente, deuda)

    assert inicio.resultado == ResultadoInicio.REQUIERE_APROBACION
    assert deuda.estado == "esperando_aprobacion"
    assert deuda.pago_iniciado_por is None
    solicitud = inicio.solicitud
    assert solicitud is not None
    assert (solicitud.monto, solicitud.moneda, solicitud.asistente_id) == (
        Decimal("80.00"),
        "PEN",
        equipo.asistente.id,
    )
    [aviso] = notificaciones_de(db, equipo.gerente)
    assert (aviso.tipo, aviso.deuda_id, aviso.urgente) == ("aprobacion_pendiente", deuda.id, False)
    [registro] = auditorias(db, deuda, "aprobacion_solicitada")
    assert registro.detalle["motivo"] == "limite_por_pago"
    assert consumo_mes_pen(db, equipo.gerente.id, AHORA) == Decimal(0)


def test_superar_el_limite_mensual_con_el_consumo_pide_aprobacion(
    db: Session, dos_gerentes: DosGerentes
) -> None:
    equipo = dos_gerentes.uno
    fijar_limite(db, equipo.gerente, mensual="200.00")
    pagada = nueva_deuda(db, equipo.gerente, monto="150.00", estado="pagada")
    nuevo_comprobante(db, pagada, equipo.asistente, "150.00", creado_en=AHORA)

    excede = nueva_deuda(db, equipo.gerente, monto="60.00")
    assert iniciar(db, equipo.asistente, excede).resultado == ResultadoInicio.REQUIERE_APROBACION
    [registro] = auditorias(db, excede, "aprobacion_solicitada")
    assert registro.detalle["motivo"] == "limite_mensual"

    justo = nueva_deuda(db, equipo.gerente, monto="50.00")
    assert iniciar(db, equipo.asistente, justo).resultado == ResultadoInicio.INICIADO


def test_la_solicitud_es_urgente_si_la_deuda_vence_hoy(
    db: Session, dos_gerentes: DosGerentes
) -> None:
    equipo = dos_gerentes.uno
    fijar_limite(db, equipo.gerente, por_pago="10.00")
    deuda = nueva_deuda(db, equipo.gerente, fecha_vencimiento=date(2026, 10, 19))
    iniciar(db, equipo.asistente, deuda)
    [aviso] = notificaciones_de(db, equipo.gerente)
    assert aviso.urgente is True


def test_usd_de_asistente_pide_aprobacion_aunque_no_haya_limite(
    db: Session, dos_gerentes: DosGerentes
) -> None:
    equipo = dos_gerentes.uno
    deuda = nueva_deuda(db, equipo.gerente, monto="40.00", moneda="USD")

    inicio = iniciar(db, equipo.asistente, deuda)

    assert inicio.resultado == ResultadoInicio.REQUIERE_APROBACION
    assert inicio.solicitud is not None
    assert (inicio.solicitud.monto, inicio.solicitud.moneda) == (Decimal("40.00"), "USD")
    [registro] = auditorias(db, deuda, "aprobacion_solicitada")
    assert registro.detalle["motivo"] == "moneda"


def test_aprobacion_del_mismo_importe_y_moneda_permite_iniciar(
    db: Session, dos_gerentes: DosGerentes
) -> None:
    equipo = dos_gerentes.uno
    deuda = nueva_deuda(db, equipo.gerente, monto="40.00", moneda="USD")
    aprobar(db, equipo, deuda, "40.00", "USD")

    inicio = iniciar(db, equipo.asistente, deuda)

    assert inicio.resultado == ResultadoInicio.INICIADO
    [registro] = auditorias(db, deuda, "pago_iniciado")
    assert registro.detalle["autorizacion"] == "aprobacion"
    # Un pago USD aprobado no se suma al consumo en soles.
    assert consumo_mes_pen(db, equipo.gerente.id, AHORA) == Decimal(0)


@pytest.mark.parametrize(("monto", "moneda"), [("30.00", "USD"), ("40.00", "PEN")])
def test_aprobacion_de_otro_importe_o_moneda_pide_otra_solicitud(
    db: Session, dos_gerentes: DosGerentes, monto: str, moneda: str
) -> None:
    equipo = dos_gerentes.uno
    deuda = nueva_deuda(db, equipo.gerente, monto="40.00", moneda="USD")
    aprobar(db, equipo, deuda, monto, moneda)

    assert iniciar(db, equipo.asistente, deuda).resultado == ResultadoInicio.REQUIERE_APROBACION


def test_el_gerente_no_tiene_limite_ni_cuenta_en_el_consumo(
    db: Session, dos_gerentes: DosGerentes
) -> None:
    equipo = dos_gerentes.uno
    fijar_limite(db, equipo.gerente, por_pago="10.00", mensual="10.00")
    soles = nueva_deuda(db, equipo.gerente, monto="1000.00")
    dolares = nueva_deuda(db, equipo.gerente, monto="500.00", moneda="USD")

    assert iniciar(db, equipo.gerente, soles).resultado == ResultadoInicio.INICIADO
    assert iniciar(db, equipo.gerente, dolares).resultado == ResultadoInicio.INICIADO
    assert consumo_mes_pen(db, equipo.gerente.id, AHORA) == Decimal(0)
    [registro] = auditorias(db, soles, "pago_iniciado")
    assert registro.detalle["autorizacion"] == "gerente"


def nueva_orden(db: Session, equipo: Equipo, deuda: Deuda, estado: str = "aceptada") -> OrdenPago:
    orden = OrdenPago(
        deuda_id=deuda.id,
        gerente_id=equipo.gerente.id,
        asistente_id=equipo.asistente.id,
        estado=estado,
        monto=deuda.monto,
        moneda=deuda.moneda,
    )
    db.add(orden)
    db.flush()
    return orden


def test_orden_aceptada_autoriza_por_encima_del_limite(
    db: Session, dos_gerentes: DosGerentes
) -> None:
    equipo = dos_gerentes.uno
    fijar_limite(db, equipo.gerente, por_pago="10.00")
    deuda = nueva_deuda(db, equipo.gerente, monto="100.00", moneda="USD")
    orden = nueva_orden(db, equipo, deuda)

    inicio = iniciar(db, equipo.asistente, deuda, orden=AutorizacionOrden(orden))

    assert inicio.resultado == ResultadoInicio.INICIADO
    [registro] = auditorias(db, deuda, "pago_iniciado")
    assert registro.detalle["autorizacion"] == "orden"
    assert registro.detalle["orden_id"] == str(orden.id)


@pytest.mark.parametrize(
    "caso", ["cancelada", "otra_deuda", "otra_asistente", "otra_moneda", "otro_monto"]
)
def test_orden_que_ya_no_autoriza_responde_409(
    db: Session, dos_gerentes: DosGerentes, caso: str
) -> None:
    equipo = dos_gerentes.uno
    deuda = nueva_deuda(db, equipo.gerente, monto="100.00")
    orden = nueva_orden(db, equipo, deuda, "cancelada" if caso == "cancelada" else "aceptada")
    if caso == "otra_deuda":
        orden.deuda_id = nueva_deuda(db, equipo.gerente).id
    if caso == "otra_asistente":
        orden.asistente_id = None
    if caso == "otra_moneda":
        orden.moneda = "USD"
    if caso == "otro_monto":
        orden.monto = Decimal("90.00")

    error = error_de(lambda: iniciar(db, equipo.asistente, deuda, orden=AutorizacionOrden(orden)))

    assert (error.status_code, error.code) == (409, "ORDEN_NO_VALIDA")
    assert deuda.estado == "pendiente"


def test_pagada_parcial_reserva_solo_el_saldo(db: Session, dos_gerentes: DosGerentes) -> None:
    equipo = dos_gerentes.uno
    fijar_limite(db, equipo.gerente, por_pago="70.00")
    deuda = nueva_deuda(db, equipo.gerente, monto="100.00", estado="pagada_parcial")
    nuevo_comprobante(db, deuda, equipo.asistente, "40.00", creado_en=AHORA)

    inicio = iniciar(db, equipo.asistente, deuda)

    assert (inicio.resultado, inicio.saldo) == (ResultadoInicio.INICIADO, Decimal("60.00"))
    # 40 de abono + 60 reservados, sin contar dos veces.
    assert consumo_mes_pen(db, equipo.gerente.id, AHORA) == Decimal("100.00")


def test_repetir_el_mismo_intento_no_duplica_efectos(
    db: Session, dos_gerentes: DosGerentes
) -> None:
    equipo = dos_gerentes.uno
    deuda = nueva_deuda(db, equipo.gerente)
    primero = iniciar(db, equipo.asistente, deuda)

    repetido = iniciar_pago(db, equipo.asistente, deuda.id, origen=ORIGEN)

    assert (repetido.resultado, repetido.repetido) == (ResultadoInicio.INICIADO, True)
    assert repetido.deuda.pago_iniciado_en == primero.deuda.pago_iniciado_en == AHORA
    assert len(auditorias(db, deuda, "pago_iniciado")) == 1


def test_repetir_con_solicitud_pendiente_devuelve_la_misma(
    db: Session, dos_gerentes: DosGerentes
) -> None:
    equipo = dos_gerentes.uno
    deuda = nueva_deuda(db, equipo.gerente, moneda="USD")
    primero = iniciar(db, equipo.asistente, deuda)
    repetido = iniciar(db, equipo.asistente, deuda)

    assert repetido.repetido is True
    assert repetido.solicitud is not None and primero.solicitud is not None
    assert repetido.solicitud.id == primero.solicitud.id
    total = db.scalar(
        select(func.count())
        .select_from(SolicitudAprobacion)
        .where(SolicitudAprobacion.deuda_id == deuda.id)
    )
    assert total == 1
    assert len(notificaciones_de(db, equipo.gerente)) == 1


def test_otro_usuario_recibe_409_si_el_pago_ya_empezo(
    db: Session, dos_gerentes: DosGerentes
) -> None:
    equipo = dos_gerentes.uno
    de_asistente = nueva_deuda(db, equipo.gerente)
    iniciar(db, equipo.asistente, de_asistente)
    error = error_de(lambda: iniciar(db, equipo.gerente, de_asistente))
    assert (error.status_code, error.code) == (409, "PAGO_EN_CURSO")

    del_gerente = nueva_deuda(db, equipo.gerente)
    iniciar(db, equipo.gerente, del_gerente)
    error = error_de(lambda: iniciar(db, equipo.asistente, del_gerente))
    assert (error.status_code, error.code) == (409, "PAGO_EN_CURSO")
    assert del_gerente.pago_iniciado_por == equipo.gerente.id


def test_solicitud_pendiente_bloquea_a_otra_persona(db: Session, dos_gerentes: DosGerentes) -> None:
    equipo = dos_gerentes.uno
    deuda = nueva_deuda(db, equipo.gerente, moneda="USD")
    iniciar(db, equipo.asistente, deuda)

    error = error_de(lambda: iniciar(db, equipo.gerente, deuda))

    assert (error.status_code, error.code) == (409, "APROBACION_PENDIENTE")
    assert deuda.estado == "esperando_aprobacion"


@pytest.mark.parametrize(
    "estado", ["esperando_recibo", "por_validar", "pagada", "anulada", "con_problema"]
)
def test_estados_que_no_permiten_iniciar(
    db: Session, dos_gerentes: DosGerentes, estado: str
) -> None:
    equipo = dos_gerentes.uno
    monto = None if estado == "esperando_recibo" else "100.00"
    deuda = nueva_deuda(db, equipo.gerente, monto=monto, estado=estado)
    error = error_de(lambda: iniciar(db, equipo.asistente, deuda))
    assert (error.status_code, error.code) == (409, "ESTADO_NO_PERMITIDO")
    assert deuda.estado == estado


@pytest.mark.parametrize("rol", ["gerente", "asistente"])
def test_la_deuda_de_otro_gerente_no_existe(
    db: Session, dos_gerentes: DosGerentes, rol: str
) -> None:
    deuda = nueva_deuda(db, dos_gerentes.uno.gerente)
    usuario = getattr(dos_gerentes.dos, rol)
    error = error_de(lambda: iniciar(db, usuario, deuda))
    assert (error.status_code, error.code) == (404, "NO_ENCONTRADO")
    assert deuda.estado == "pendiente"


def test_sin_saldo_no_se_inicia(db: Session, dos_gerentes: DosGerentes) -> None:
    equipo = dos_gerentes.uno
    deuda = nueva_deuda(db, equipo.gerente, monto="50.00")
    nuevo_comprobante(db, deuda, equipo.asistente, "50.00")
    error = error_de(lambda: iniciar(db, equipo.asistente, deuda))
    assert (error.status_code, error.code) == (409, "SIN_SALDO")


def test_el_indice_impide_una_segunda_solicitud_pendiente(
    db: Session, dos_gerentes: DosGerentes
) -> None:
    # Dato inconsistente: solicitud pendiente con la deuda ya pendiente. El índice único responde.
    equipo = dos_gerentes.uno
    deuda = nueva_deuda(db, equipo.gerente, moneda="USD")
    db.add(SolicitudAprobacion(deuda_id=deuda.id, asistente_id=equipo.asistente.id, monto=1))
    db.flush()

    error = error_de(lambda: iniciar(db, equipo.asistente, deuda))

    assert (error.status_code, error.code) == (409, "APROBACION_PENDIENTE")
    assert deuda.estado == "pendiente"


@pytest.mark.parametrize("rol", ["gerente", "asistente"])
def test_la_deuda_esperando_recibo_sin_monto_no_se_inicia_hasta_confirmar_el_importe(
    db: Session, dos_gerentes: DosGerentes, rol: str
) -> None:
    equipo = dos_gerentes.uno
    usuario = getattr(equipo, rol)
    deuda = nueva_deuda(db, equipo.gerente, monto=None, estado="esperando_recibo")
    consumo = consumo_mes_pen(db, equipo.gerente.id, AHORA)

    error = error_de(lambda: iniciar(db, usuario, deuda))

    assert (error.status_code, error.code) == (409, "ESTADO_NO_PERMITIDO")
    assert "aún no tiene monto" in error.detail
    assert (deuda.estado, deuda.pago_iniciado_por, deuda.monto) == ("esperando_recibo", None, None)
    assert auditorias(db, deuda, "pago_iniciado") == []
    assert consumo_mes_pen(db, equipo.gerente.id, AHORA) == consumo
    assert acciones_de_pago(db, deuda, usuario).iniciar is False

    deuda.monto = Decimal("120.00")
    deuda.estado = "pendiente"
    assert acciones_de_pago(db, deuda, usuario).iniciar is True
    assert iniciar(db, usuario, deuda).saldo == Decimal("120.00")
