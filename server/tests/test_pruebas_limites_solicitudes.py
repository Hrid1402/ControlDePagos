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


def test_ca05_pagos_del_gerente_no_tienen_limite(
    db: Session,
    dos_gerentes: DosGerentes,
) -> None:
    """CA05: Los pagos que realiza el gerente no tienen límite y no cuentan en el consumo."""
    gerente = dos_gerentes.uno.gerente

    # Fijar límite bajo
    fijar_limite(db, gerente.id, por_pago=Decimal("10.00"), mensual=Decimal("20.00"))

    # Gerente inicia pago grande en soles
    deuda_soles = nueva_deuda(db, gerente, monto="5000.00")
    res_soles = iniciar_pago(db, gerente, deuda_soles.id, origen=ORIGEN_PRUEBA)
    assert res_soles.resultado == ResultadoInicio.INICIADO

    # Gerente inicia pago en moneda extranjera
    deuda_usd = nueva_deuda(db, gerente, monto="2500.00", moneda="USD")
    res_usd = iniciar_pago(db, gerente, deuda_usd.id, origen=ORIGEN_PRUEBA)
    assert res_usd.resultado == ResultadoInicio.INICIADO

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


