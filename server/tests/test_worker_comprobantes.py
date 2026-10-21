"""Worker de validación de comprobantes (H24 CA03, TASK-85).

Las tareas corren con la sesión de la prueba y un OCR de reemplazo. Se prueban el resultado, la
idempotencia ante una tarea repetida, los reintentos limitados y la recuperación programada.
"""

import uuid
from collections.abc import Iterator
from datetime import timedelta

import pytest
from celery.canvas import Signature
from celery.exceptions import SoftTimeLimitExceeded
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errores import ErrorApi
from app.core.eventos import Evento
from app.core.tiempo import ahora_lima
from app.models import Comprobante, Deuda, Notificacion
from app.ocr.motor import ErrorOcr, LecturaOcr, Linea
from app.services.validacion import (
    ACCION_A_SEGUIR,
    MENSAJE_FORMATO_DESCONOCIDO,
    MENSAJE_SIN_LECTURA,
)
from app.workers import base
from app.workers import comprobantes as modulo
from tests.conftest import DosGerentes, Equipo, S3EnMemoria, nueva_deuda, nuevo_comprobante
from tests.ejemplos_comprobantes import EJEMPLOS

# Legible pero de una entidad que no se valida sola: queda en revisión del gerente.
LEGIBLE = next(e for e in EJEMPLOS if e.nombre == "entidad_desconocida").lectura()


@pytest.fixture
def sesion_de_prueba(db: Session, monkeypatch: pytest.MonkeyPatch) -> Iterator[Session]:
    """Las tareas usan la sesión de la prueba: confirman sobre su savepoint y no dejan datos."""

    class Fabrica:
        def __enter__(self) -> Session:
            return db

        def __exit__(self, *_: object) -> None:
            return None

    monkeypatch.setattr(base, "fabrica_sesiones", Fabrica)
    monkeypatch.setattr(modulo, "BLOQUEO_RECUPERAR", f"pruebas-recuperar-{uuid.uuid4().hex}")
    yield db


def leyendo(monkeypatch: pytest.MonkeyPatch, resultado: LecturaOcr | Exception) -> list[str]:
    """Reemplaza el OCR: devuelve resultado o lo lanza. Devuelve la lista de lecturas hechas."""
    hechas: list[str] = []

    def leer(contenido: bytes, extension: str) -> LecturaOcr:
        hechas.append(extension)
        if isinstance(resultado, Exception):
            raise resultado
        return resultado

    monkeypatch.setattr(modulo, "leer_documento", leer)
    return hechas


def procesando(db: Session, equipo: Equipo, s3: S3EnMemoria) -> tuple[Comprobante, Deuda]:
    deuda = nueva_deuda(db, equipo.gerente, estado="por_validar")
    deuda.pago_iniciado_por = equipo.asistente.id
    comprobante = nuevo_comprobante(db, deuda, equipo.asistente, "100.00", estado="procesando")
    s3.objetos[comprobante.archivo_url] = (b"imagen", "image/jpeg")
    return comprobante, deuda


def notificaciones(db: Session, tipo: str) -> list[Notificacion]:
    return list(db.scalars(select(Notificacion).where(Notificacion.tipo == tipo)))


def test_un_comprobante_legible_pasa_a_revision_del_gerente(
    sesion_de_prueba: Session,
    dos_gerentes: DosGerentes,
    s3: S3EnMemoria,
    publicados: list[tuple[uuid.UUID, Evento]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db, equipo = sesion_de_prueba, dos_gerentes.uno
    comprobante, deuda = procesando(db, equipo, s3)
    leyendo(monkeypatch, LEGIBLE)

    assert modulo.procesar_comprobante.apply(args=(str(comprobante.id),)).get() == "en_revision"

    db.refresh(comprobante)
    db.refresh(deuda)
    assert (comprobante.estado, comprobante.motivo_codigo) == ("en_revision", None)
    assert comprobante.texto_ocr is not None
    assert comprobante.texto_ocr.startswith("Caja Municipal\n")
    assert str(comprobante.confianza) == "0.980"
    assert (comprobante.entidad, comprobante.numero_operacion) == ("otra", None)
    assert comprobante.datos_extraidos["observacion"] == MENSAJE_FORMATO_DESCONOCIDO
    assert deuda.estado == "por_validar"
    (aviso,) = notificaciones(db, "comprobante_en_revision")
    assert (aviso.usuario_id, aviso.deuda_id) == (equipo.gerente.id, deuda.id)
    resultado = [(u, e.datos) for u, e in publicados if e.tipo == "comprobante_resultado"]
    assert [u for u, _ in resultado] == [equipo.asistente.id, equipo.gerente.id]
    assert resultado[0][1]["deudas"] == [{"deuda_id": str(deuda.id), "estado": "por_validar"}]


@pytest.mark.parametrize(
    "lectura",
    [LecturaOcr([], paginas=1), LecturaOcr([Linea("~#", 0.4), Linea("BC", 0.7)], paginas=1)],
    ids=["sin texto", "confianza baja"],
)
def test_un_comprobante_ilegible_se_rechaza_y_la_deuda_vuelve_al_intento(
    sesion_de_prueba: Session,
    dos_gerentes: DosGerentes,
    s3: S3EnMemoria,
    publicados: list[tuple[uuid.UUID, Evento]],
    monkeypatch: pytest.MonkeyPatch,
    lectura: LecturaOcr,
) -> None:
    db, equipo = sesion_de_prueba, dos_gerentes.uno
    comprobante, deuda = procesando(db, equipo, s3)
    deuda.recordatorios_enviados = 2
    leyendo(monkeypatch, lectura)

    assert modulo.procesar_comprobante.apply(args=(str(comprobante.id),)).get() == "rechazado"

    db.refresh(comprobante)
    db.refresh(deuda)
    assert (comprobante.estado, comprobante.motivo_codigo) == ("rechazado", "ilegible")
    assert (deuda.estado, deuda.recordatorios_enviados) == ("en_proceso", 0)
    (aviso,) = notificaciones(db, "comprobante_rechazado")
    assert aviso.usuario_id == equipo.asistente.id
    assert aviso.mensaje == ACCION_A_SEGUIR["ilegible"]


def test_el_rechazo_no_libera_una_deuda_que_cubre_otro_comprobante(
    sesion_de_prueba: Session,
    dos_gerentes: DosGerentes,
    s3: S3EnMemoria,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db, equipo = sesion_de_prueba, dos_gerentes.uno
    comprobante, deuda = procesando(db, equipo, s3)
    nuevo_comprobante(db, deuda, equipo.asistente, "20.00", estado="en_revision")
    leyendo(monkeypatch, LecturaOcr([], paginas=1))

    modulo.procesar_comprobante.apply(args=(str(comprobante.id),)).get()

    db.refresh(deuda)
    assert deuda.estado == "por_validar"


def test_repetir_la_tarea_no_vuelve_a_leer_ni_a_avisar(
    sesion_de_prueba: Session,
    dos_gerentes: DosGerentes,
    s3: S3EnMemoria,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db, equipo = sesion_de_prueba, dos_gerentes.uno
    comprobante, _ = procesando(db, equipo, s3)
    hechas = leyendo(monkeypatch, LEGIBLE)

    modulo.procesar_comprobante.apply(args=(str(comprobante.id),)).get()
    assert modulo.procesar_comprobante.apply(args=(str(comprobante.id),)).get() is None
    assert modulo.procesar_comprobante.apply(args=(str(uuid.uuid4()),)).get() is None

    assert hechas == ["jpg"]
    assert len(notificaciones(db, "comprobante_en_revision")) == 1


@pytest.mark.parametrize(
    "fallo",
    [
        ErrorOcr("no convierte"),
        SoftTimeLimitExceeded(),
        ErrorApi(503, "ARCHIVO_NO_DISPONIBLE", "No se pudo leer el archivo."),
    ],
    ids=["ocr", "timeout", "s3"],
)
def test_un_fallo_de_lectura_se_reintenta_y_luego_queda_en_revision(
    sesion_de_prueba: Session,
    dos_gerentes: DosGerentes,
    s3: S3EnMemoria,
    monkeypatch: pytest.MonkeyPatch,
    fallo: Exception,
) -> None:
    """Celery reintenta en el acto al ejecutar con apply: se ven todos los intentos juntos."""
    db, equipo = sesion_de_prueba, dos_gerentes.uno
    comprobante, deuda = procesando(db, equipo, s3)
    hechas = leyendo(monkeypatch, fallo)

    assert modulo.procesar_comprobante.apply(args=(str(comprobante.id),)).get() == "en_revision"

    assert len(hechas) == modulo.MAXIMO_REINTENTOS + 1
    db.refresh(comprobante)
    db.refresh(deuda)
    assert comprobante.datos_extraidos["observacion"] == MENSAJE_SIN_LECTURA
    assert deuda.estado == "por_validar"


def test_un_fallo_pasajero_se_resuelve_en_el_reintento(
    sesion_de_prueba: Session,
    dos_gerentes: DosGerentes,
    s3: S3EnMemoria,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db, equipo = sesion_de_prueba, dos_gerentes.uno
    comprobante, _ = procesando(db, equipo, s3)
    resultados: list[LecturaOcr | Exception] = [SoftTimeLimitExceeded(), LEGIBLE]

    def leer(contenido: bytes, extension: str) -> LecturaOcr:
        resultado = resultados.pop(0)
        if isinstance(resultado, Exception):
            raise resultado
        return resultado

    monkeypatch.setattr(modulo, "leer_documento", leer)

    assert modulo.procesar_comprobante.apply(args=(str(comprobante.id),)).get() == "en_revision"

    db.refresh(comprobante)
    assert comprobante.datos_extraidos["observacion"] == MENSAJE_FORMATO_DESCONOCIDO


def test_la_recuperacion_vuelve_a_encolar_los_comprobantes_perdidos(
    sesion_de_prueba: Session,
    dos_gerentes: DosGerentes,
    s3: S3EnMemoria,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db, equipo = sesion_de_prueba, dos_gerentes.uno
    perdido, _ = procesando(db, equipo, s3)
    resuelto = nuevo_comprobante(
        db, nueva_deuda(db, equipo.gerente), equipo.asistente, "5.00", estado="validado"
    )
    encoladas: list[Signature] = []
    monkeypatch.setattr(modulo, "encolar", lambda firma: encoladas.append(firma) or True)

    # Recién subido: todavía es de su tarea original.
    assert modulo.recuperar_comprobantes.apply().get() == 0

    monkeypatch.setattr(modulo, "ahora_lima", lambda: ahora_lima() + timedelta(minutes=11))
    assert modulo.recuperar_comprobantes.apply().get() == 1

    assert [f.args for f in encoladas] == [(str(perdido.id),)]
    db.refresh(perdido)
    db.refresh(resuelto)
    assert perdido.datos_extraidos["recuperaciones"] == 1
    assert resuelto.estado == "validado"


def test_tras_varias_recuperaciones_queda_en_revision(
    sesion_de_prueba: Session,
    dos_gerentes: DosGerentes,
    s3: S3EnMemoria,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db, equipo = sesion_de_prueba, dos_gerentes.uno
    perdido, _ = procesando(db, equipo, s3)
    perdido.datos_extraidos = {"recuperaciones": modulo.MAXIMO_RECUPERACIONES}
    db.flush()
    encoladas: list[Signature] = []
    monkeypatch.setattr(modulo, "encolar", lambda firma: encoladas.append(firma) or True)
    monkeypatch.setattr(modulo, "ahora_lima", lambda: ahora_lima() + timedelta(minutes=11))

    modulo.recuperar_comprobantes.apply().get()

    db.refresh(perdido)
    assert (perdido.estado, encoladas) == ("en_revision", [])
    assert perdido.datos_extraidos["observacion"] == MENSAJE_SIN_LECTURA


def test_la_recuperacion_no_corre_dos_veces_a_la_vez(
    sesion_de_prueba: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    with base.un_solo_a_la_vez(modulo.BLOQUEO_RECUPERAR) as tomado:
        assert tomado
        assert modulo.recuperar_comprobantes.apply().get() is None
