"""Pruebas de límites y solicitudes (H05, TASK-26).

Cubre los criterios de aceptación CA01 a CA12:
CA01 a CA05: Límites por pago/mensual, importes opcionales, consumo del mes y pagos del gerente.
CA06 a CA08: Solicitud de aprobación por exceder límite, resolución y motivo opcional.
CA09 a CA12: Recordatorios urgentes, listado por estado, reinicio mensual y persistencia.
"""

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.dependencias import Origen
from app.core.errores import ErrorApi
from app.services.limites import fijar_limite, obtener_limite
from app.services.pagos import ResultadoInicio, iniciar_pago
from app.services.saldo import consumo_mes_pen
from tests.conftest import DosGerentes, nueva_deuda

ORIGEN_PRUEBA = Origen(dispositivo="pruebas", ip="127.0.0.1")
AHORA_LIMA = datetime(2026, 10, 20, 10, 0, 0, tzinfo=UTC)


def test_ca01_y_ca03_limites_aplican_a_asistente_y_vacio_es_sin_limite(
    db: Session,
    dos_gerentes: DosGerentes,
) -> None:
    """CA01 y CA03: Aplican a la asistente activa; un campo vacío (None) significa sin límite."""
    # 1. Sin límite configurado: asistente puede pagar sin tope (CA03)
    gerente_sin_limite = dos_gerentes.dos.gerente
    asistente_sin_limite = dos_gerentes.dos.asistente
    deuda_alta = nueva_deuda(db, gerente_sin_limite, monto="50000.00")
    resultado = iniciar_pago(db, asistente_sin_limite, deuda_alta.id, origen=ORIGEN_PRUEBA)
    assert resultado.resultado == ResultadoInicio.INICIADO

    # 2. Configurar límite por pago y mensual para la asistente activa (CA01)
    equipo = dos_gerentes.uno
    gerente = equipo.gerente
    asistente = equipo.asistente

    fijar_limite(db, gerente.id, por_pago=Decimal("100.00"), mensual=Decimal("1000.00"))
    db.commit()

    limite = obtener_limite(db, gerente.id)
    assert limite is not None
    assert limite.por_pago == Decimal("100.00")
    assert limite.mensual == Decimal("1000.00")

    # Pago dentro del límite por pago inicia directamente
    deuda_ok = nueva_deuda(db, gerente, monto="80.00")
    res_ok = iniciar_pago(db, asistente, deuda_ok.id, origen=ORIGEN_PRUEBA)
    assert res_ok.resultado == ResultadoInicio.INICIADO


def test_ca02_monto_en_soles_y_por_pago_no_supera_mensual(
    db: Session,
    dos_gerentes: DosGerentes,
) -> None:
    """CA02: Los montos van en soles y el límite por pago no puede ser mayor que el mensual."""
    gerente = dos_gerentes.uno.gerente

    # Error si por_pago > mensual
    with pytest.raises(ErrorApi) as exc:
        fijar_limite(db, gerente.id, por_pago=Decimal("500.00"), mensual=Decimal("400.00"))
    assert exc.value.status_code == 400
    assert exc.value.code == "LIMITE_INVALIDO"

    # Montos con 2 decimales válidos
    guardado = fijar_limite(db, gerente.id, por_pago=Decimal("120.50"), mensual=Decimal("600.00"))
    assert guardado.por_pago == Decimal("120.50")
    assert guardado.mensual == Decimal("600.00")


def test_ca04_consumo_del_mes_frente_al_limite(
    db: Session,
    dos_gerentes: DosGerentes,
) -> None:
    """CA04: Se calcula y muestra el consumo del mes (abonos + reservas) frente al límite."""
    equipo = dos_gerentes.uno
    gerente = equipo.gerente
    asistente = equipo.asistente

    fijar_limite(db, gerente.id, por_pago=Decimal("200.00"), mensual=Decimal("500.00"))

    # Deuda en proceso reservada por la asistente
    d1 = nueva_deuda(db, gerente, monto="150.00")
    iniciar_pago(db, asistente, d1.id, origen=ORIGEN_PRUEBA)

    # El consumo del mes incluye los 150.00 reservados
    consumo = consumo_mes_pen(db, gerente.id, AHORA_LIMA)
    assert consumo == Decimal("150.00")

    # Una segunda deuda que junto con el consumo exceda el mensual (150 + 400 = 550 > 500)
    d2 = nueva_deuda(db, gerente, monto="400.00")
    # Pero también excede por_pago (400 > 200), pide aprobación
    res_excede = iniciar_pago(db, asistente, d2.id, origen=ORIGEN_PRUEBA)
    assert res_excede.resultado == ResultadoInicio.REQUIERE_APROBACION


def test_ca05_el_gerente_no_inicia_pagos_ni_suma_al_consumo(
    db: Session,
    dos_gerentes: DosGerentes,
) -> None:
    """CA05 tras TASK-109: el gerente ya no paga; sus intentos responden 403 y no suman."""
    gerente = dos_gerentes.uno.gerente

    # Fijar límite bajo
    fijar_limite(db, gerente.id, por_pago=Decimal("10.00"), mensual=Decimal("20.00"))

    # Gerente inicia pago grande en soles
    for deuda in (
        nueva_deuda(db, gerente, monto="5000.00"),
        nueva_deuda(db, gerente, monto="2500.00", moneda="USD"),
    ):
        with pytest.raises(ErrorApi) as error:
            iniciar_pago(db, gerente, deuda.id, origen=ORIGEN_PRUEBA)
        assert error.value.code == "SIN_PERMISO"

    # No computa en el consumo del mes de la asistente
    assert consumo_mes_pen(db, gerente.id, AHORA_LIMA) == Decimal("0")


def test_ca06_superar_limite_crea_solicitud_y_deuda_esperando_aprobacion(
    db: Session,
    dos_gerentes: DosGerentes,
) -> None:
    """CA06: Si supera el límite, crea solicitud de aprobación y la deuda queda esperando."""
    equipo = dos_gerentes.uno
    gerente = equipo.gerente
    asistente = equipo.asistente

    fijar_limite(db, gerente.id, por_pago=Decimal("100.00"), mensual=Decimal("500.00"))
    deuda = nueva_deuda(db, gerente, monto="150.00")

    res = iniciar_pago(db, asistente, deuda.id, origen=ORIGEN_PRUEBA)
    assert res.resultado == ResultadoInicio.REQUIERE_APROBACION
    assert res.solicitud is not None
    assert res.solicitud.monto == Decimal("150.00")
    assert res.solicitud.deuda_id == deuda.id
    assert res.solicitud.asistente_id == asistente.id
    assert res.solicitud.estado == "pendiente"

    db.refresh(deuda)
    assert deuda.estado == "esperando_aprobacion"


def test_ca07_gerente_aprueba_solicitud_y_permite_inicio_de_pago(
    db: Session,
    dos_gerentes: DosGerentes,
) -> None:
    """CA07: El gerente aprueba la solicitud y luego la asistente puede iniciar el pago."""
    from app.services.limites import resolver_solicitud

    equipo = dos_gerentes.uno
    gerente = equipo.gerente
    asistente = equipo.asistente

    fijar_limite(db, gerente.id, por_pago=Decimal("50.00"), mensual=Decimal("500.00"))
    deuda = nueva_deuda(db, gerente, monto="80.00")

    # 1. Requiere aprobación inicial
    res_inicio = iniciar_pago(db, asistente, deuda.id, origen=ORIGEN_PRUEBA)
    assert res_inicio.resultado == ResultadoInicio.REQUIERE_APROBACION
    assert res_inicio.solicitud is not None

    # 2. Gerente aprueba la solicitud
    sol_resuelta = resolver_solicitud(db, gerente, res_inicio.solicitud.id, "aprobada")
    assert sol_resuelta.estado == "aprobada"
    assert sol_resuelta.resuelta_por == gerente.id
    assert sol_resuelta.resuelta_en is not None

    # 3. Con la aprobación vigente, la asistente puede iniciar el pago
    res_segundo = iniciar_pago(db, asistente, deuda.id, origen=ORIGEN_PRUEBA)
    assert res_segundo.resultado == ResultadoInicio.INICIADO
    db.refresh(deuda)
    assert deuda.estado == "en_proceso"


def test_ca08_gerente_rechaza_solicitud_con_motivo_opcional_y_notifica(
    db: Session,
    dos_gerentes: DosGerentes,
) -> None:
    """CA08: Al rechazar se guarda el motivo opcional y la asistente es notificada."""
    from app.models import Notificacion
    from app.services.limites import resolver_solicitud

    equipo = dos_gerentes.uno
    gerente = equipo.gerente
    asistente = equipo.asistente

    fijar_limite(db, gerente.id, por_pago=Decimal("30.00"))
    deuda = nueva_deuda(db, gerente, monto="60.00")

    res_inicio = iniciar_pago(db, asistente, deuda.id, origen=ORIGEN_PRUEBA)
    assert res_inicio.solicitud is not None

    # Rechazar con motivo opcional
    sol_rechazada = resolver_solicitud(
        db,
        gerente,
        res_inicio.solicitud.id,
        "rechazada",
        motivo="Monto no justificado para este mes",
    )
    assert sol_rechazada.estado == "rechazada"
    assert sol_rechazada.motivo == "Monto no justificado para este mes"

    # Verificar notificación para la asistente
    notif = db.scalar(
        select(Notificacion).where(
            Notificacion.usuario_id == asistente.id,
            Notificacion.deuda_id == deuda.id,
        )
    )
    assert notif is not None
    assert "rechazó" in notif.mensaje

    # Intentar resolver nuevamente falla con 409
    with pytest.raises(ErrorApi) as exc:
        resolver_solicitud(db, gerente, res_inicio.solicitud.id, "aprobada")
    assert exc.value.status_code == 409
    assert exc.value.code == "SOLICITUD_YA_RESUELTA"


def test_ca09_recordatorios_solicitud_urgente_si_deuda_vence_hoy(
    db: Session,
    dos_gerentes: DosGerentes,
) -> None:
    """CA09: Si no se responde, envía recordatorio; urgente si la deuda vence ese día."""
    from app.models import Notificacion
    from app.services.limites import recordar_solicitud

    equipo = dos_gerentes.uno
    gerente = equipo.gerente
    asistente = equipo.asistente
    fijar_limite(db, gerente.id, por_pago=Decimal("10.00"), mensual=Decimal("500.00"))

    hoy = date(2026, 10, 20)
    manana = date(2026, 10, 21)

    # 1. Deuda que vence mañana: recordatorio no urgente
    d_manana = nueva_deuda(db, gerente, monto="50.00", fecha_vencimiento=manana)
    res1 = iniciar_pago(db, asistente, d_manana.id, origen=ORIGEN_PRUEBA)
    assert res1.solicitud is not None

    sol1 = recordar_solicitud(db, res1.solicitud.id, hoy=hoy)
    assert sol1.recordatorios_enviados == 1

    notif_manana = db.scalar(
        select(Notificacion)
        .where(Notificacion.deuda_id == d_manana.id, Notificacion.usuario_id == gerente.id)
        .order_by(Notificacion.id.desc())
    )
    assert notif_manana is not None
    assert notif_manana.urgente is False

    # 2. Deuda que vence hoy: recordatorio urgente
    d_hoy = nueva_deuda(db, gerente, monto="60.00", fecha_vencimiento=hoy)
    res2 = iniciar_pago(db, asistente, d_hoy.id, origen=ORIGEN_PRUEBA)
    assert res2.solicitud is not None

    sol2 = recordar_solicitud(db, res2.solicitud.id, hoy=hoy)
    assert sol2.recordatorios_enviados == 1

    notif_hoy = db.scalar(
        select(Notificacion)
        .where(Notificacion.deuda_id == d_hoy.id, Notificacion.usuario_id == gerente.id)
        .order_by(Notificacion.id.desc())
    )
    assert notif_hoy is not None
    assert notif_hoy.urgente is True


def test_ca10_listas_de_solicitudes_por_estado(
    db: Session,
    dos_gerentes: DosGerentes,
) -> None:
    """CA10: Hay listas de solicitudes clasificadas en pendientes, aprobadas y rechazadas."""
    from app.services.limites import resolver_solicitud, solicitudes_de_gerente

    equipo = dos_gerentes.uno
    gerente = equipo.gerente
    asistente = equipo.asistente
    fijar_limite(db, gerente.id, por_pago=Decimal("10.00"))

    # Crear 3 solicitudes
    d1 = nueva_deuda(db, gerente, monto="20.00")
    d2 = nueva_deuda(db, gerente, monto="30.00")
    d3 = nueva_deuda(db, gerente, monto="40.00")

    s1 = iniciar_pago(db, asistente, d1.id, origen=ORIGEN_PRUEBA).solicitud
    s2 = iniciar_pago(db, asistente, d2.id, origen=ORIGEN_PRUEBA).solicitud
    s3 = iniciar_pago(db, asistente, d3.id, origen=ORIGEN_PRUEBA).solicitud
    assert s1 and s2 and s3

    # Dejar s1 en pendiente, aprobar s2, rechazar s3
    resolver_solicitud(db, gerente, s2.id, "aprobada")
    resolver_solicitud(db, gerente, s3.id, "rechazada")

    pendientes = solicitudes_de_gerente(db, gerente.id, estado="pendiente")
    aprobadas = solicitudes_de_gerente(db, gerente.id, estado="aprobada")
    rechazadas = solicitudes_de_gerente(db, gerente.id, estado="rechazada")
    todas = solicitudes_de_gerente(db, gerente.id)

    assert [s.id for s in pendientes] == [s1.id]
    assert [s.id for s in aprobadas] == [s2.id]
    assert [s.id for s in rechazadas] == [s3.id]
    assert len(todas) == 3


def test_ca11_limite_mensual_se_reinicia_el_dia_uno(
    db: Session,
    dos_gerentes: DosGerentes,
) -> None:
    """CA11: El límite mensual se reinicia el día 1; consumos de meses previos no restan."""
    from tests.conftest import nuevo_comprobante

    equipo = dos_gerentes.uno
    gerente = equipo.gerente
    asistente = equipo.asistente

    # Deuda pagada en septiembre con comprobante validado subido en septiembre
    d_sep = nueva_deuda(db, gerente, monto="300.00", estado="pagada")
    nuevo_comprobante(
        db,
        d_sep,
        asistente,
        "300.00",
        creado_en=datetime(2026, 9, 25, 12, 0, 0, tzinfo=UTC),
    )

    # En septiembre el consumo era 300.00
    fecha_sep = datetime(2026, 9, 30, 15, 0, 0, tzinfo=UTC)
    assert consumo_mes_pen(db, gerente.id, fecha_sep) == Decimal("300.00")

    # Al llegar el 1 de octubre, el consumo del mes se reinicia a 0.00
    fecha_oct = datetime(2026, 10, 1, 8, 0, 0, tzinfo=UTC)
    assert consumo_mes_pen(db, gerente.id, fecha_oct) == Decimal("0.00")


def test_ca12_cambiar_limite_no_afecta_solicitudes_ya_enviadas(
    db: Session,
    dos_gerentes: DosGerentes,
) -> None:
    """CA12: Modificar los límites no altera los montos ni estados de solicitudes ya emitidas."""
    equipo = dos_gerentes.uno
    gerente = equipo.gerente
    asistente = equipo.asistente

    fijar_limite(db, gerente.id, por_pago=Decimal("50.00"), mensual=Decimal("500.00"))
    deuda = nueva_deuda(db, gerente, monto="120.00")

    res = iniciar_pago(db, asistente, deuda.id, origen=ORIGEN_PRUEBA)
    assert res.solicitud is not None
    sol_id = res.solicitud.id

    # El gerente incrementa sus límites a un valor superior a la deuda
    fijar_limite(db, gerente.id, por_pago=Decimal("200.00"), mensual=Decimal("1500.00"))
    db.commit()

    # La solicitud previa conserva su monto original y su estado pendiente intactos
    db.refresh(res.solicitud)
    assert res.solicitud.id == sol_id
    assert res.solicitud.monto == Decimal("120.00")
    assert res.solicitud.estado == "pendiente"
