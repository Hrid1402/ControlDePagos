from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models import Usuario
from app.services.saldo import (
    consumo_mes_pen,
    rango_mes,
    saldo_de,
    tiene_comprobante_activo,
)
from tests.conftest import DosGerentes, nueva_deuda, nuevo_comprobante

# Lima es UTC-5 todo el año: las horas de Lima se expresan aquí en UTC.
AHORA = datetime(2026, 10, 19, 17, 0, tzinfo=UTC)  # 19/10 12:00 en Lima
FIN_OCTUBRE = datetime(2026, 11, 1, 4, 59, tzinfo=UTC)  # 31/10 23:59 en Lima
INICIO_NOVIEMBRE = datetime(2026, 11, 1, 5, 0, tzinfo=UTC)  # 01/11 00:00 en Lima
FIN_SETIEMBRE = datetime(2026, 10, 1, 4, 0, tzinfo=UTC)  # 30/09 23:00 en Lima


def test_saldo_sin_abonos_es_el_monto(db: Session, dos_gerentes: DosGerentes) -> None:
    deuda = nueva_deuda(db, dos_gerentes.uno.gerente, monto="120.50")
    assert saldo_de(db, deuda) == Decimal("120.50")


def test_saldo_resta_solo_los_comprobantes_validados(
    db: Session, dos_gerentes: DosGerentes
) -> None:
    equipo = dos_gerentes.uno
    deuda = nueva_deuda(db, equipo.gerente, monto="100.00", estado="pagada_parcial")
    nuevo_comprobante(db, deuda, equipo.asistente, "30.00")
    for estado in ("procesando", "en_revision", "rechazado", "por_confirmar"):
        nuevo_comprobante(db, deuda, equipo.asistente, "10.00", estado=estado)
    assert saldo_de(db, deuda) == Decimal("70.00")


def test_rango_mes_se_corta_en_hora_de_lima() -> None:
    inicio, fin = rango_mes(FIN_OCTUBRE)
    assert (inicio.isoformat(), fin.isoformat()) == (
        "2026-10-01T00:00:00-05:00",
        "2026-11-01T00:00:00-05:00",
    )
    inicio, fin = rango_mes(datetime(2026, 12, 31, 12, 0, tzinfo=UTC))
    assert (inicio.month, fin.year, fin.month) == (12, 2027, 1)


def test_consumo_cuenta_solo_abonos_pen_validados_de_asistente_en_el_mes(
    db: Session, dos_gerentes: DosGerentes
) -> None:
    equipo = dos_gerentes.uno
    pen = nueva_deuda(db, equipo.gerente, monto="500.00", estado="pagada_parcial")
    nuevo_comprobante(db, pen, equipo.asistente, "40.00", creado_en=AHORA)
    # No cuentan: pago del gerente, comprobante sin validar, mes anterior y USD.
    nuevo_comprobante(db, pen, equipo.gerente, "25.00", creado_en=AHORA)
    nuevo_comprobante(db, pen, equipo.asistente, "15.00", estado="en_revision", creado_en=AHORA)
    nuevo_comprobante(db, pen, equipo.asistente, "60.00", creado_en=FIN_SETIEMBRE)
    usd = nueva_deuda(db, equipo.gerente, monto="80.00", moneda="USD", estado="pagada_parcial")
    nuevo_comprobante(db, usd, equipo.asistente, "20.00", creado_en=AHORA)

    assert consumo_mes_pen(db, equipo.gerente.id, AHORA) == Decimal("40.00")


def test_consumo_respeta_el_borde_del_mes_en_lima(db: Session, dos_gerentes: DosGerentes) -> None:
    equipo = dos_gerentes.uno
    deuda = nueva_deuda(db, equipo.gerente, monto="500.00", estado="pagada_parcial")
    nuevo_comprobante(db, deuda, equipo.asistente, "10.00", creado_en=FIN_OCTUBRE)
    nuevo_comprobante(db, deuda, equipo.asistente, "20.00", creado_en=INICIO_NOVIEMBRE)

    assert consumo_mes_pen(db, equipo.gerente.id, FIN_OCTUBRE) == Decimal("10.00")
    assert consumo_mes_pen(db, equipo.gerente.id, INICIO_NOVIEMBRE) == Decimal("20.00")


def test_consumo_suma_reservas_sin_contar_dos_veces_el_abono(
    db: Session, dos_gerentes: DosGerentes
) -> None:
    equipo = dos_gerentes.uno
    en_proceso = nueva_deuda(db, equipo.gerente, monto="100.00", estado="en_proceso")
    en_proceso.pago_iniciado_por = equipo.asistente.id
    nuevo_comprobante(db, en_proceso, equipo.asistente, "30.00", creado_en=AHORA)
    por_validar = nueva_deuda(db, equipo.gerente, monto="50.00", estado="por_validar")
    por_validar.pago_iniciado_por = equipo.asistente.id
    # No reservan: intento del gerente y deuda USD.
    del_gerente = nueva_deuda(db, equipo.gerente, monto="900.00", estado="en_proceso")
    del_gerente.pago_iniciado_por = equipo.gerente.id
    usd = nueva_deuda(db, equipo.gerente, monto="70.00", moneda="USD", estado="en_proceso")
    usd.pago_iniciado_por = equipo.asistente.id
    db.flush()

    # 30 de abono + 70 de saldo reservado + 50 por validar.
    assert consumo_mes_pen(db, equipo.gerente.id, AHORA) == Decimal("150.00")


def test_consumo_es_del_gerente_y_sigue_tras_cambiar_de_asistente(
    db: Session, dos_gerentes: DosGerentes
) -> None:
    equipo = dos_gerentes.uno
    deuda = nueva_deuda(db, equipo.gerente, monto="300.00", estado="pagada_parcial")
    nuevo_comprobante(db, deuda, equipo.asistente, "45.00", creado_en=AHORA)
    equipo.asistente.estado = "inactiva"
    db.flush()
    nueva = Usuario(
        rol="asistente", gerente_id=equipo.gerente.id, username="asistente_nueva", password_hash="x"
    )
    db.add(nueva)
    db.flush()
    nuevo_comprobante(db, deuda, nueva, "5.00", creado_en=AHORA)
    otra = nueva_deuda(db, dos_gerentes.dos.gerente, monto="300.00", estado="pagada_parcial")
    nuevo_comprobante(db, otra, dos_gerentes.dos.asistente, "99.00", creado_en=AHORA)

    assert consumo_mes_pen(db, equipo.gerente.id, AHORA) == Decimal("50.00")
    assert consumo_mes_pen(db, dos_gerentes.dos.gerente.id, AHORA) == Decimal("99.00")


def test_comprobante_activo_por_reparto_o_por_sugerencia(
    db: Session, dos_gerentes: DosGerentes
) -> None:
    equipo = dos_gerentes.uno
    deuda = nueva_deuda(db, equipo.gerente)
    nuevo_comprobante(db, deuda, equipo.asistente, "10.00", estado="rechazado")
    nuevo_comprobante(db, deuda, equipo.asistente, "10.00", estado="validado")
    assert tiene_comprobante_activo(db, deuda.id) is False

    nuevo_comprobante(db, deuda, equipo.asistente, "10.00", estado="procesando")
    assert tiene_comprobante_activo(db, deuda.id) is True

    sugerida = nueva_deuda(db, equipo.gerente)
    otra = nueva_deuda(db, equipo.gerente)
    comprobante = nuevo_comprobante(db, otra, equipo.asistente, "10.00", estado="en_revision")
    comprobante.deuda_sugerida_id = sugerida.id
    db.flush()
    assert tiene_comprobante_activo(db, sugerida.id) is True
