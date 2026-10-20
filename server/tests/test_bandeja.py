import uuid
from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.dependencias import Origen
from app.core.errores import ErrorApi
from app.core.paginacion import Paginacion
from app.core.tiempo import zona_horaria
from app.models import Auditoria, Deuda, Usuario
from app.services.bandeja import (
    Bandeja,
    Etiqueta,
    Pestana,
    consultar_bandeja,
    manana_a_las_ocho,
    recordar_manana,
)
from tests.conftest import (
    DosGerentes,
    nueva_categoria,
    nueva_deuda,
    nueva_orden,
    nuevo_comprobante,
)

ORIGEN = Origen(dispositivo="pruebas", ip=None)
# Lima es UTC-5 todo el año: las horas de Lima se expresan aquí en UTC.
AHORA = datetime(2026, 10, 19, 17, 0, tzinfo=UTC)  # 19/10 12:00 en Lima
INICIO_PAGO = AHORA - timedelta(hours=2)
MANANA_OCHO = datetime(2026, 10, 20, 13, 0, tzinfo=UTC)  # 20/10 08:00 en Lima
HOY = date(2026, 10, 19)


def bandeja(
    db: Session,
    gerente: Usuario,
    pestana: Pestana = Pestana.POR_PAGAR,
    ahora: datetime = AHORA,
    categoria_id: uuid.UUID | None = None,
) -> Bandeja:
    return consultar_bandeja(
        db, gerente.id, pestana, Paginacion(page=1, size=100), categoria_id, ahora
    )


def ids(resultado: Bandeja) -> list[uuid.UUID]:
    return [fila.deuda.id for fila in resultado.filas]


def contadores(resultado: Bandeja) -> tuple[int, int, int]:
    c = resultado.contadores
    return c[Pestana.POR_PAGAR], c[Pestana.POR_VALIDAR], c[Pestana.RECHAZADAS]


def en_proceso(db: Session, deuda: Deuda, usuario: Usuario) -> Deuda:
    deuda.estado = "en_proceso"
    deuda.pago_iniciado_por = usuario.id
    deuda.pago_iniciado_en = INICIO_PAGO
    db.flush()
    return deuda


def test_ordena_los_seis_niveles_con_su_etiqueta(db: Session, dos_gerentes: DosGerentes) -> None:
    gerente = dos_gerentes.uno.gerente
    proxima = nueva_deuda(db, gerente, fecha_vencimiento=date(2026, 10, 25))
    tarjeta = nueva_deuda(
        db, gerente, fecha_vencimiento=date(2026, 10, 28), tipo_categoria="tarjeta"
    )
    hoy = nueva_deuda(db, gerente, fecha_vencimiento=HOY)
    vencida = nueva_deuda(db, gerente, fecha_vencimiento=date(2026, 10, 15))
    fijada = nueva_deuda(db, gerente, fecha_vencimiento=date(2026, 10, 30))
    fijada.fijada = True
    urgente = nueva_deuda(db, gerente, fecha_vencimiento=date(2026, 10, 31))
    nueva_orden(db, urgente)

    resultado = bandeja(db, gerente)

    assert ids(resultado) == [urgente.id, fijada.id, vencida.id, hoy.id, tarjeta.id, proxima.id]
    assert [(f.nivel, f.etiqueta) for f in resultado.filas] == list(enumerate(Etiqueta))
    assert [f.dias_restantes for f in resultado.filas] == [12, 11, -4, 0, 9, 6]


def test_urgente_va_antes_que_fijada_aunque_esta_venza_antes(
    db: Session, dos_gerentes: DosGerentes
) -> None:
    gerente = dos_gerentes.uno.gerente
    fijada = nueva_deuda(db, gerente, fecha_vencimiento=date(2026, 10, 10))
    fijada.fijada = True
    urgente = nueva_deuda(db, gerente, fecha_vencimiento=date(2026, 10, 30))
    nueva_orden(db, urgente)
    fijada_y_urgente = nueva_deuda(db, gerente, fecha_vencimiento=date(2026, 11, 5))
    fijada_y_urgente.fijada = True
    nueva_orden(db, fijada_y_urgente)

    resultado = bandeja(db, gerente)

    assert ids(resultado) == [urgente.id, fijada_y_urgente.id, fijada.id]
    assert [f.etiqueta for f in resultado.filas] == [
        Etiqueta.ORDEN_URGENTE,
        Etiqueta.ORDEN_URGENTE,
        Etiqueta.FIJADA,
    ]


@pytest.mark.parametrize(
    ("estado", "etiqueta"),
    [
        ("enviada", Etiqueta.ORDEN_URGENTE),
        ("vista", Etiqueta.ORDEN_URGENTE),
        ("aceptada", Etiqueta.ORDEN_URGENTE),
        ("rechazada", Etiqueta.PROXIMA),
        ("pagada", Etiqueta.PROXIMA),
        ("cancelada", Etiqueta.PROXIMA),
    ],
)
def test_solo_una_orden_abierta_es_urgente(
    db: Session, dos_gerentes: DosGerentes, estado: str, etiqueta: Etiqueta
) -> None:
    gerente = dos_gerentes.uno.gerente
    deuda = nueva_deuda(db, gerente)
    orden = nueva_orden(db, deuda, estado=estado)

    (fila,) = bandeja(db, gerente).filas

    assert fila.etiqueta == etiqueta
    assert (fila.orden is not None) == (etiqueta == Etiqueta.ORDEN_URGENTE)
    if fila.orden is not None:
        assert fila.orden.id == orden.id


def test_vence_hoy_usa_la_fecha_de_lima(db: Session, dos_gerentes: DosGerentes) -> None:
    gerente = dos_gerentes.uno.gerente
    noche = datetime(2026, 10, 20, 4, 30, tzinfo=UTC)  # 19/10 23:30 en Lima, 20/10 en UTC
    hoy = nueva_deuda(db, gerente, fecha_vencimiento=HOY)
    manana = nueva_deuda(db, gerente, fecha_vencimiento=date(2026, 10, 20))

    resultado = bandeja(db, gerente, ahora=noche)

    assert [(f.deuda.id, f.etiqueta, f.dias_restantes) for f in resultado.filas] == [
        (hoy.id, Etiqueta.VENCE_HOY, 0),
        (manana.id, Etiqueta.PROXIMA, 1),
    ]


def test_desempate_por_plazo_de_la_orden_vencimiento_e_id(
    db: Session, dos_gerentes: DosGerentes
) -> None:
    gerente = dos_gerentes.uno.gerente
    sin_plazo = nueva_deuda(db, gerente, fecha_vencimiento=date(2026, 10, 20))
    nueva_orden(db, sin_plazo)
    plazo_tarde = nueva_deuda(db, gerente, fecha_vencimiento=date(2026, 10, 21))
    nueva_orden(db, plazo_tarde, plazo=AHORA + timedelta(hours=3))
    plazo_pronto = nueva_deuda(db, gerente, fecha_vencimiento=date(2026, 10, 22))
    nueva_orden(db, plazo_pronto, plazo=AHORA + timedelta(hours=1))
    mismas = [nueva_deuda(db, gerente, fecha_vencimiento=date(2026, 10, 26)) for _ in range(3)]
    antes = nueva_deuda(db, gerente, fecha_vencimiento=date(2026, 10, 25))

    resultado = bandeja(db, gerente)

    assert ids(resultado) == [
        plazo_pronto.id,
        plazo_tarde.id,
        sin_plazo.id,
        antes.id,
        *sorted(d.id for d in mismas),
    ]


@pytest.mark.parametrize(
    ("ahora", "esperado"),
    [
        (AHORA, MANANA_OCHO),
        (datetime(2026, 10, 20, 4, 59, tzinfo=UTC), MANANA_OCHO),  # 19/10 23:59 en Lima
        # 20/10 00:30 en Lima: ya es el día siguiente, reaparece el 21 a las 08:00.
        (datetime(2026, 10, 20, 5, 30, tzinfo=UTC), datetime(2026, 10, 21, 13, 0, tzinfo=UTC)),
    ],
)
def test_manana_a_las_ocho_de_lima(ahora: datetime, esperado: datetime) -> None:
    resultado = manana_a_las_ocho(ahora)

    assert resultado == esperado
    assert resultado.tzinfo == zona_horaria()


def test_pospuesta_reaparece_a_las_ocho_de_lima(db: Session, dos_gerentes: DosGerentes) -> None:
    equipo = dos_gerentes.uno
    deuda = nueva_deuda(db, equipo.gerente)

    recordar_manana(db, equipo.asistente, deuda.id, origen=ORIGEN, ahora=AHORA)

    assert deuda.oculta_hasta == MANANA_OCHO
    antes = bandeja(db, equipo.gerente, ahora=MANANA_OCHO - timedelta(seconds=1))
    assert (ids(antes), contadores(antes)) == ([], (0, 0, 0))
    despues = bandeja(db, equipo.gerente, ahora=MANANA_OCHO)
    assert (ids(despues), contadores(despues)) == ([deuda.id], (1, 0, 0))


def test_no_se_pospone_una_deuda_con_orden_urgente(db: Session, dos_gerentes: DosGerentes) -> None:
    equipo = dos_gerentes.uno
    deuda = nueva_deuda(db, equipo.gerente)
    nueva_orden(db, deuda, estado="vista")

    with pytest.raises(ErrorApi) as error:
        recordar_manana(db, equipo.asistente, deuda.id, origen=ORIGEN, ahora=AHORA)

    assert (error.value.status_code, error.value.code) == (409, "ORDEN_URGENTE_ACTIVA")
    assert deuda.oculta_hasta is None


def test_orden_que_llega_despues_muestra_la_pospuesta(
    db: Session, dos_gerentes: DosGerentes
) -> None:
    equipo = dos_gerentes.uno
    deuda = nueva_deuda(db, equipo.gerente)
    recordar_manana(db, equipo.asistente, deuda.id, origen=ORIGEN, ahora=AHORA)
    assert ids(bandeja(db, equipo.gerente)) == []

    nueva_orden(db, deuda)

    resultado = bandeja(db, equipo.gerente)
    assert [(f.deuda.id, f.etiqueta) for f in resultado.filas] == [
        (deuda.id, Etiqueta.ORDEN_URGENTE)
    ]
    assert contadores(resultado) == (1, 0, 0)


def test_pospuesta_que_empieza_a_pagarse_sigue_visible(
    db: Session, dos_gerentes: DosGerentes
) -> None:
    equipo = dos_gerentes.uno
    deuda = nueva_deuda(db, equipo.gerente)
    recordar_manana(db, equipo.asistente, deuda.id, origen=ORIGEN, ahora=AHORA)

    en_proceso(db, deuda, equipo.gerente)

    assert ids(bandeja(db, equipo.gerente)) == [deuda.id]


@pytest.mark.parametrize(
    "estado", ["en_proceso", "esperando_aprobacion", "con_problema", "por_validar", "pagada"]
)
def test_solo_se_pospone_lo_pendiente_de_pago(
    db: Session, dos_gerentes: DosGerentes, estado: str
) -> None:
    equipo = dos_gerentes.uno
    deuda = nueva_deuda(db, equipo.gerente, estado=estado)

    with pytest.raises(ErrorApi) as error:
        recordar_manana(db, equipo.asistente, deuda.id, origen=ORIGEN, ahora=AHORA)

    assert (error.value.status_code, error.value.code) == (409, "ESTADO_NO_PERMITIDO")


def test_posponer_dos_veces_el_mismo_dia_audita_una_vez(
    db: Session, dos_gerentes: DosGerentes
) -> None:
    equipo = dos_gerentes.uno
    deuda = nueva_deuda(db, equipo.gerente, estado="pagada_parcial")

    recordar_manana(db, equipo.asistente, deuda.id, origen=ORIGEN, ahora=AHORA)
    recordar_manana(db, equipo.asistente, deuda.id, origen=ORIGEN, ahora=AHORA + timedelta(hours=5))

    eventos = db.scalars(
        select(Auditoria).where(
            Auditoria.entidad_id == deuda.id, Auditoria.accion == "deuda_pospuesta"
        )
    ).all()
    assert [e.detalle for e in eventos] == [{"oculta_hasta": "2026-10-20T08:00:00-05:00"}]
    assert eventos[0].usuario_id == equipo.asistente.id


@pytest.mark.parametrize(
    ("estado", "pestana"),
    [
        ("pendiente", Pestana.POR_PAGAR),
        ("pagada_parcial", Pestana.POR_PAGAR),
        ("esperando_aprobacion", Pestana.POR_PAGAR),
        ("con_problema", Pestana.POR_PAGAR),
        ("por_validar", Pestana.POR_VALIDAR),
        ("esperando_recibo", None),
        ("pagada", None),
        ("anulada", None),
    ],
)
def test_pestana_segun_el_estado_de_la_deuda(
    db: Session, dos_gerentes: DosGerentes, estado: str, pestana: Pestana | None
) -> None:
    gerente = dos_gerentes.uno.gerente
    deuda = nueva_deuda(db, gerente, estado=estado)

    for p in Pestana:
        resultado = bandeja(db, gerente, p)
        esperado = [deuda.id] if p == pestana else []
        assert (ids(resultado), resultado.total) == (esperado, len(esperado))


@pytest.mark.parametrize(
    ("comprobante", "pestana"),
    [
        (None, Pestana.POR_PAGAR),
        ("procesando", Pestana.POR_VALIDAR),
        ("en_revision", Pestana.POR_VALIDAR),
        ("por_confirmar", Pestana.POR_VALIDAR),
        ("rechazado", Pestana.RECHAZADAS),
    ],
)
def test_pestana_de_en_proceso_segun_el_comprobante_del_intento(
    db: Session, dos_gerentes: DosGerentes, comprobante: str | None, pestana: Pestana
) -> None:
    equipo = dos_gerentes.uno
    deuda = en_proceso(db, nueva_deuda(db, equipo.gerente), equipo.asistente)
    if comprobante is not None:
        nuevo_comprobante(
            db,
            deuda,
            equipo.asistente,
            "100.00",
            estado=comprobante,
            creado_en=INICIO_PAGO + timedelta(hours=1),
        )

    resultado = bandeja(db, equipo.gerente, pestana)

    assert ids(resultado) == [deuda.id]
    assert resultado.filas[0].comprobante_estado == comprobante
    assert sum(contadores(resultado)) == 1


def test_rechazo_de_un_intento_anterior_no_cuenta(db: Session, dos_gerentes: DosGerentes) -> None:
    equipo = dos_gerentes.uno
    deuda = en_proceso(db, nueva_deuda(db, equipo.gerente), equipo.asistente)
    nuevo_comprobante(
        db,
        deuda,
        equipo.asistente,
        "100.00",
        estado="rechazado",
        creado_en=INICIO_PAGO - timedelta(days=1),
    )

    resultado = bandeja(db, equipo.gerente)

    assert ids(resultado) == [deuda.id]
    assert contadores(resultado) == (1, 0, 0)


def test_reemplazo_pasa_de_rechazadas_a_por_validar(db: Session, dos_gerentes: DosGerentes) -> None:
    equipo = dos_gerentes.uno
    deuda = en_proceso(db, nueva_deuda(db, equipo.gerente), equipo.asistente)
    rechazado = nuevo_comprobante(
        db,
        deuda,
        equipo.asistente,
        "100.00",
        estado="rechazado",
        creado_en=INICIO_PAGO + timedelta(minutes=30),
    )
    rechazadas = bandeja(db, equipo.gerente, Pestana.RECHAZADAS)
    assert (ids(rechazadas), contadores(rechazadas)) == ([deuda.id], (0, 0, 1))

    reemplazo = nuevo_comprobante(
        db,
        deuda,
        equipo.asistente,
        "100.00",
        estado="procesando",
        creado_en=INICIO_PAGO + timedelta(minutes=50),
    )
    reemplazo.reemplaza_a_id = rechazado.id
    db.flush()

    assert ids(bandeja(db, equipo.gerente, Pestana.RECHAZADAS)) == []
    por_validar = bandeja(db, equipo.gerente, Pestana.POR_VALIDAR)
    assert (ids(por_validar), contadores(por_validar)) == ([deuda.id], (0, 1, 0))
    assert por_validar.filas[0].comprobante_estado == "procesando"


def test_contadores_no_cuentan_pospuestas_ni_deudas_fuera(
    db: Session, dos_gerentes: DosGerentes
) -> None:
    equipo = dos_gerentes.uno
    gerente = equipo.gerente
    nueva_deuda(db, gerente)
    nueva_deuda(db, gerente, estado="con_problema")
    pospuesta = nueva_deuda(db, gerente)
    recordar_manana(db, equipo.asistente, pospuesta.id, origen=ORIGEN, ahora=AHORA)
    nueva_deuda(db, gerente, estado="por_validar")
    rechazada = en_proceso(db, nueva_deuda(db, gerente), equipo.asistente)
    nuevo_comprobante(
        db, rechazada, equipo.asistente, "100.00", estado="rechazado", creado_en=AHORA
    )
    for estado in ("pagada", "anulada", "esperando_recibo"):
        nueva_deuda(db, gerente, estado=estado)
    nueva_deuda(db, dos_gerentes.dos.gerente)

    resultado = bandeja(db, gerente)

    assert contadores(resultado) == (2, 1, 1)
    assert resultado.total == len(resultado.filas) == 2


def test_filtro_por_categoria_aplica_a_lista_y_contadores(
    db: Session, dos_gerentes: DosGerentes
) -> None:
    gerente = dos_gerentes.uno.gerente
    luz = nueva_categoria(db, gerente)
    primera = nueva_deuda(db, gerente, categoria=luz, fecha_vencimiento=date(2026, 10, 22))
    segunda = nueva_deuda(db, gerente, categoria=luz, fecha_vencimiento=date(2026, 10, 23))
    nueva_deuda(db, gerente, categoria=luz, estado="por_validar")
    nueva_deuda(db, gerente)
    nueva_deuda(db, gerente, estado="por_validar")

    resultado = bandeja(db, gerente, categoria_id=luz.id)

    assert ids(resultado) == [primera.id, segunda.id]
    assert contadores(resultado) == (2, 1, 0)


def test_categoria_de_otro_gerente_responde_404(db: Session, dos_gerentes: DosGerentes) -> None:
    ajena = nueva_categoria(db, dos_gerentes.dos.gerente)

    with pytest.raises(ErrorApi) as error:
        bandeja(db, dos_gerentes.uno.gerente, categoria_id=ajena.id)

    assert (error.value.status_code, error.value.code, error.value.field) == (
        404,
        "NO_ENCONTRADO",
        "categoria",
    )


def test_saldo_descuenta_solo_abonos_validados(db: Session, dos_gerentes: DosGerentes) -> None:
    equipo = dos_gerentes.uno
    deuda = nueva_deuda(db, equipo.gerente, monto="120.00", estado="pagada_parcial")
    nuevo_comprobante(db, deuda, equipo.asistente, "50.00")
    nuevo_comprobante(db, deuda, equipo.asistente, "30.00", estado="rechazado")

    (fila,) = bandeja(db, equipo.gerente).filas

    assert fila.saldo == 70
