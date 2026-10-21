"""Extracción aplicada al comprobante y duplicado por número de operación (H24 CA04, TASK-86).

aplicar_lectura se llama con el comprobante bloqueado, como lo hace el worker de OCR.
"""

from decimal import Decimal

from sqlalchemy.orm import Session

from app.models import Comprobante, Deuda, Notificacion
from app.ocr.motor import LecturaOcr, Linea
from app.services.validacion import (
    ACCION_A_SEGUIR,
    MENSAJE_FORMATO_DESCONOCIDO,
    MENSAJE_SIN_REGLAS,
    aplicar_lectura,
    bloquear_comprobante,
)
from tests.conftest import DosGerentes, Equipo, nueva_deuda, nuevo_comprobante
from tests.ejemplos_comprobantes import EJEMPLOS, lima

BCP = next(e for e in EJEMPLOS if e.nombre == "bcp_app")


def procesando(db: Session, equipo: Equipo) -> tuple[Comprobante, Deuda]:
    deuda = nueva_deuda(db, equipo.gerente, monto="85.40", estado="por_validar")
    comprobante = nuevo_comprobante(db, deuda, equipo.asistente, "85.40", estado="procesando")
    return comprobante, deuda


def aplicar(db: Session, comprobante: Comprobante, lectura: LecturaOcr) -> Comprobante:
    bloqueado = bloquear_comprobante(db, comprobante.id)
    assert bloqueado is not None
    assert aplicar_lectura(db, bloqueado, lectura)
    db.flush()
    return bloqueado


def test_guarda_los_campos_extraidos_del_comprobante(
    db: Session, dos_gerentes: DosGerentes
) -> None:
    comprobante, _ = procesando(db, dos_gerentes.uno)

    resultado = aplicar(db, comprobante, BCP.lectura())

    assert (resultado.estado, resultado.motivo_codigo) == ("en_revision", None)
    assert resultado.datos_extraidos["observacion"] == MENSAJE_SIN_REGLAS
    assert (resultado.entidad, resultado.numero_operacion) == ("bcp", "00456789")
    assert resultado.monto == Decimal("85.40")
    assert resultado.fecha_pago == lima(2026, 10, 20, 10, 35)
    campos = resultado.datos_extraidos["campos"]
    assert campos["empresa"] == {"valor": "HIDRANDINA", "confianza": 0.98}
    assert campos["codigo"]["valor"] == "12345678"
    assert resultado.datos_extraidos["faltantes"] == []


def test_un_formato_desconocido_va_a_revision_sin_guardar_la_operacion(
    db: Session, dos_gerentes: DosGerentes
) -> None:
    comprobante, _ = procesando(db, dos_gerentes.uno)
    desconocido = next(e for e in EJEMPLOS if e.nombre == "entidad_desconocida")

    resultado = aplicar(db, comprobante, desconocido.lectura())

    assert (resultado.estado, resultado.entidad) == ("en_revision", "otra")
    assert resultado.numero_operacion is None
    assert resultado.datos_extraidos["observacion"] == MENSAJE_FORMATO_DESCONOCIDO


def test_un_campo_clave_ausente_va_a_revision_y_lo_nombra(
    db: Session, dos_gerentes: DosGerentes
) -> None:
    comprobante, _ = procesando(db, dos_gerentes.uno)
    lectura = LecturaOcr(
        [Linea("BCP", 0.98), Linea("Empresa: HIDRANDINA", 0.98), Linea("S/ 85.40", 0.97)], 1
    )

    resultado = aplicar(db, comprobante, lectura)

    assert resultado.estado == "en_revision"
    assert resultado.datos_extraidos["observacion"] == (
        "No se pudo leer el código de suministro y la fecha del comprobante: lo revisa el gerente."
    )


def test_la_misma_operacion_dos_veces_indica_en_que_deuda_se_uso(
    db: Session, dos_gerentes: DosGerentes
) -> None:
    equipo = dos_gerentes.uno
    primero, deuda_primera = procesando(db, equipo)
    aplicar(db, primero, BCP.lectura())
    segundo, deuda_segunda = procesando(db, equipo)
    deuda_segunda.pago_iniciado_por = equipo.asistente.id

    resultado = aplicar(db, segundo, BCP.lectura())

    assert (resultado.estado, resultado.motivo_codigo) == ("rechazado", "duplicado")
    assert resultado.numero_operacion is None
    mensaje = resultado.datos_extraidos["observacion"]
    assert mensaje.startswith("Este comprobante ya se usó en Hidrandina ")
    assert "(octubre 2026)" in mensaje
    assert resultado.datos_extraidos["duplicado_de"] == {
        "comprobante_id": str(primero.id),
        "deudas": [str(deuda_primera.id)],
    }
    db.refresh(deuda_segunda)
    assert deuda_segunda.estado == "en_proceso"
    aviso = db.query(Notificacion).filter_by(tipo="comprobante_rechazado").one()
    assert aviso.mensaje == mensaje


def test_el_duplicado_de_otro_gerente_no_dice_donde_se_uso(
    db: Session, dos_gerentes: DosGerentes
) -> None:
    ajeno, _ = procesando(db, dos_gerentes.dos)
    aplicar(db, ajeno, BCP.lectura())
    propio, _ = procesando(db, dos_gerentes.uno)

    resultado = aplicar(db, propio, BCP.lectura())

    assert (resultado.estado, resultado.motivo_codigo) == ("rechazado", "duplicado")
    assert resultado.datos_extraidos["observacion"] == ACCION_A_SEGUIR["duplicado"]
    assert "duplicado_de" not in resultado.datos_extraidos


def test_una_operacion_de_un_comprobante_rechazado_se_puede_usar(
    db: Session, dos_gerentes: DosGerentes
) -> None:
    equipo = dos_gerentes.uno
    anterior, _ = procesando(db, equipo)
    anterior.entidad, anterior.numero_operacion, anterior.estado = "bcp", "00456789", "rechazado"
    db.flush()
    comprobante, _ = procesando(db, equipo)

    resultado = aplicar(db, comprobante, BCP.lectura())

    assert (resultado.estado, resultado.numero_operacion) == ("en_revision", "00456789")


def test_el_mismo_numero_en_otra_entidad_no_es_duplicado(
    db: Session, dos_gerentes: DosGerentes
) -> None:
    equipo = dos_gerentes.uno
    otro, _ = procesando(db, equipo)
    otro.entidad, otro.numero_operacion = "interbank", "00456789"
    db.flush()
    comprobante, _ = procesando(db, equipo)

    resultado = aplicar(db, comprobante, BCP.lectura())

    assert resultado.estado == "en_revision"


def test_un_comprobante_resuelto_no_se_vuelve_a_aplicar(
    db: Session, dos_gerentes: DosGerentes
) -> None:
    comprobante, _ = procesando(db, dos_gerentes.uno)
    aplicar(db, comprobante, BCP.lectura())

    bloqueado = bloquear_comprobante(db, comprobante.id)
    assert bloqueado is not None
    assert aplicar_lectura(db, bloqueado, LecturaOcr([], 1)) is False
    assert bloqueado.estado == "en_revision"
