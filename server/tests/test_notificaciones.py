import uuid
from datetime import UTC, date, datetime, time
from decimal import Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.eventos import Evento
from app.models import Categoria, Deuda, Notificacion, PreferenciaNotificacion, Servicio, Usuario
from app.schemas.notificaciones import NotificacionSalida
from app.services.notificaciones import TipoNotificacion, en_silencio, notificar
from tests.conftest import DosGerentes

Publicados = list[tuple[uuid.UUID, Evento]]

# Horas de Lima (UTC-5) expresadas en UTC, como las da datetime.now(UTC).
LIMA_02_00 = datetime(2026, 10, 19, 7, 0, tzinfo=UTC)
LIMA_12_00 = datetime(2026, 10, 19, 17, 0, tzinfo=UTC)
LIMA_22_30 = datetime(2026, 10, 20, 3, 30, tzinfo=UTC)


def crear_deuda(db: Session, gerente: Usuario) -> Deuda:
    categoria = Categoria(gerente_id=gerente.id, nombre="Luz", tipo="servicio_variable")
    db.add(categoria)
    db.flush()
    servicio = Servicio(
        gerente_id=gerente.id,
        categoria_id=categoria.id,
        empresa_nombre="Hidrandina",
        codigo_suministro=f"S-{gerente.username}",
    )
    db.add(servicio)
    db.flush()
    deuda = Deuda(
        gerente_id=gerente.id,
        servicio_id=servicio.id,
        periodo=date(2026, 10, 1),
        monto=Decimal("120.50"),
        fecha_vencimiento=date(2026, 10, 25),
    )
    db.add(deuda)
    db.flush()
    return deuda


def desactivar(db: Session, usuario: Usuario, tipo: TipoNotificacion, canal: str = "app") -> None:
    db.add(
        PreferenciaNotificacion(usuario_id=usuario.id, tipo=tipo.value, canal=canal, activa=False)
    )
    db.flush()


def total_de(db: Session, usuario: Usuario) -> int:
    return (
        db.scalar(
            select(func.count())
            .select_from(Notificacion)
            .where(Notificacion.usuario_id == usuario.id)
        )
        or 0
    )


def silenciar(db: Session, usuario: Usuario, desde: time | None, hasta: time | None) -> None:
    usuario.silencio_desde = desde
    usuario.silencio_hasta = hasta
    db.flush()


def test_crea_la_notificacion_y_emite_el_evento_tras_el_commit(
    db: Session, dos_gerentes: DosGerentes, publicados: Publicados
) -> None:
    gerente = dos_gerentes.uno.gerente
    deuda = crear_deuda(db, gerente)
    notificacion = notificar(
        db, gerente, TipoNotificacion.DEUDA_CREADA, "Deuda creada", "Luz de octubre", deuda.id
    )
    assert notificacion is not None
    assert (notificacion.usuario_id, notificacion.deuda_id) == (gerente.id, deuda.id)
    assert (notificacion.tipo, notificacion.urgente) == ("deuda_creada", False)
    assert notificacion.leida_en is None
    assert notificacion.creado_en is not None
    assert publicados == []

    db.commit()
    [(destinatario, evento)] = publicados
    assert destinatario == gerente.id
    assert evento.tipo == "notificacion"
    assert evento.datos["id"] == str(notificacion.id)
    assert evento.datos["deuda_id"] == str(deuda.id)
    assert evento.datos["titulo"] == "Deuda creada"
    assert evento.datos["mensaje"] == "Luz de octubre"
    assert evento.datos["leida"] is False
    assert evento.datos["aviso"] is True


def test_la_asistente_recibe_avisos_de_las_deudas_de_su_gerente(
    db: Session, dos_gerentes: DosGerentes
) -> None:
    uno = dos_gerentes.uno
    deuda = crear_deuda(db, uno.gerente)
    notificacion = notificar(
        db, uno.asistente, TipoNotificacion.COMENTARIO, "Nuevo", "Hola", deuda.id
    )
    assert notificacion is not None
    assert notificacion.usuario_id == uno.asistente.id


@pytest.mark.parametrize("destinatario", ["gerente", "asistente"])
def test_no_se_notifica_sobre_la_deuda_de_otro_gerente(
    db: Session, dos_gerentes: DosGerentes, publicados: Publicados, destinatario: str
) -> None:
    ajena = crear_deuda(db, dos_gerentes.dos.gerente)
    usuario = getattr(dos_gerentes.uno, destinatario)
    with pytest.raises(ValueError, match="no pertenece"):
        notificar(db, usuario, TipoNotificacion.DEUDA_CREADA, "Deuda", "Ajena", ajena.id)
    db.commit()
    assert total_de(db, usuario) == 0
    assert publicados == []


def test_una_deuda_inexistente_no_se_acepta(db: Session, dos_gerentes: DosGerentes) -> None:
    with pytest.raises(ValueError):
        notificar(
            db, dos_gerentes.uno.gerente, TipoNotificacion.VENCIDA, "Vencida", "x", uuid.uuid4()
        )


@pytest.mark.parametrize("campo", ["estado", "eliminado_en"])
def test_una_cuenta_inactiva_o_eliminada_no_recibe(
    db: Session, dos_gerentes: DosGerentes, publicados: Publicados, campo: str
) -> None:
    asistente = dos_gerentes.uno.asistente
    if campo == "estado":
        asistente.estado = "inactiva"
    else:
        asistente.eliminado_en = datetime.now(UTC)
    db.flush()
    assert (
        notificar(db, asistente, TipoNotificacion.ORDEN_URGENTE, "Urgente", "x", urgente=True)
        is None
    )
    db.commit()
    assert total_de(db, asistente) == 0
    assert publicados == []


def test_una_preferencia_desactivada_no_genera_notificacion(
    db: Session, dos_gerentes: DosGerentes, publicados: Publicados
) -> None:
    gerente = dos_gerentes.uno.gerente
    desactivar(db, gerente, TipoNotificacion.DEUDA_CREADA)
    assert notificar(db, gerente, TipoNotificacion.DEUDA_CREADA, "Deuda", "x") is None
    db.commit()
    assert total_de(db, gerente) == 0
    assert publicados == []


def test_la_preferencia_desactivada_solo_afecta_a_su_tipo(
    db: Session, dos_gerentes: DosGerentes
) -> None:
    gerente = dos_gerentes.uno.gerente
    desactivar(db, gerente, TipoNotificacion.DEUDA_CREADA)
    assert notificar(db, gerente, TipoNotificacion.VENCIDA, "Vencida", "x") is not None


def test_una_urgente_se_guarda_y_emite_aunque_su_preferencia_este_desactivada(
    db: Session, dos_gerentes: DosGerentes, publicados: Publicados
) -> None:
    gerente = dos_gerentes.uno.gerente
    desactivar(db, gerente, TipoNotificacion.APROBACION_PENDIENTE)
    notificacion = notificar(
        db, gerente, TipoNotificacion.APROBACION_PENDIENTE, "Aprobación", "x", urgente=True
    )
    db.commit()
    assert notificacion is not None
    assert total_de(db, gerente) == 1
    [(_, evento)] = publicados
    assert evento.datos["urgente"] is True
    assert evento.datos["aviso"] is True


def test_otro_canal_desactivado_no_afecta_a_la_app(db: Session, dos_gerentes: DosGerentes) -> None:
    gerente = dos_gerentes.uno.gerente
    desactivar(db, gerente, TipoNotificacion.DEUDA_PAGADA, canal="correo")
    desactivar(db, gerente, TipoNotificacion.DEUDA_PAGADA, canal="whatsapp")
    assert notificar(db, gerente, TipoNotificacion.DEUDA_PAGADA, "Pagada", "x") is not None


def test_la_preferencia_de_otro_usuario_no_afecta(db: Session, dos_gerentes: DosGerentes) -> None:
    desactivar(db, dos_gerentes.dos.gerente, TipoNotificacion.NO_PUDE_PAGAR)
    gerente = dos_gerentes.uno.gerente
    assert notificar(db, gerente, TipoNotificacion.NO_PUDE_PAGAR, "No pudo", "x") is not None


def test_en_silencio_se_guarda_sin_aviso(
    db: Session, dos_gerentes: DosGerentes, publicados: Publicados
) -> None:
    gerente = dos_gerentes.uno.gerente
    silenciar(db, gerente, time(22, 0), time(7, 0))
    notificacion = notificar(
        db, gerente, TipoNotificacion.POR_VENCER, "Por vencer", "x", ahora=LIMA_22_30
    )
    db.commit()
    assert notificacion is not None
    assert total_de(db, gerente) == 1
    [(_, evento)] = publicados
    assert evento.datos["aviso"] is False


def test_en_silencio_una_urgente_avisa(
    db: Session, dos_gerentes: DosGerentes, publicados: Publicados
) -> None:
    asistente = dos_gerentes.uno.asistente
    silenciar(db, asistente, time(22, 0), time(7, 0))
    notificar(
        db, asistente, TipoNotificacion.ORDEN_URGENTE, "Orden", "x", urgente=True, ahora=LIMA_02_00
    )
    db.commit()
    [(_, evento)] = publicados
    assert evento.datos["aviso"] is True


def test_fuera_del_silencio_se_avisa(
    db: Session, dos_gerentes: DosGerentes, publicados: Publicados
) -> None:
    gerente = dos_gerentes.uno.gerente
    silenciar(db, gerente, time(22, 0), time(7, 0))
    notificar(db, gerente, TipoNotificacion.VENCIDA, "Vencida", "x", ahora=LIMA_12_00)
    db.commit()
    [(_, evento)] = publicados
    assert evento.datos["aviso"] is True


@pytest.mark.parametrize(
    ("desde", "hasta", "ahora", "esperado"),
    [
        (time(22, 0), time(7, 0), LIMA_22_30, True),
        (time(22, 0), time(7, 0), LIMA_02_00, True),
        (time(22, 0), time(7, 0), LIMA_12_00, False),
        (time(22, 0), time(7, 0), datetime(2026, 10, 19, 12, 0, tzinfo=UTC), False),  # 07:00
        (time(22, 0), time(7, 0), datetime(2026, 10, 20, 3, 0, tzinfo=UTC), True),  # 22:00
        (time(9, 0), time(13, 0), LIMA_12_00, True),
        (time(9, 0), time(13, 0), LIMA_22_30, False),
        (None, None, LIMA_02_00, False),
        (time(22, 0), None, LIMA_22_30, False),
        (None, time(7, 0), LIMA_02_00, False),
        (time(8, 0), time(8, 0), LIMA_12_00, False),
    ],
)
def test_horario_silencioso_en_hora_de_lima(
    desde: time | None, hasta: time | None, ahora: datetime, esperado: bool
) -> None:
    usuario = Usuario(silencio_desde=desde, silencio_hasta=hasta)
    assert en_silencio(usuario, ahora) is esperado


def test_la_misma_clave_de_evento_no_duplica_ni_vuelve_a_avisar(
    db: Session, dos_gerentes: DosGerentes, publicados: Publicados
) -> None:
    gerente = dos_gerentes.uno.gerente
    deuda = crear_deuda(db, gerente)
    clave = f"por_vencer:{deuda.id}:2026-10-22"
    primera = notificar(
        db, gerente, TipoNotificacion.POR_VENCER, "Vence", "x", deuda.id, clave_evento=clave
    )
    db.commit()
    # El job se repite: no hay segunda notificación ni segundo evento.
    repetida = notificar(
        db, gerente, TipoNotificacion.POR_VENCER, "Vence", "x", deuda.id, clave_evento=clave
    )
    db.commit()
    assert primera is not None
    assert primera.clave_evento == clave
    assert repetida is None
    assert total_de(db, gerente) == 1
    assert len(publicados) == 1


def test_la_misma_clave_para_otro_destinatario_si_se_crea(
    db: Session, dos_gerentes: DosGerentes
) -> None:
    uno = dos_gerentes.uno
    clave = "comentario:123"
    assert notificar(db, uno.gerente, TipoNotificacion.COMENTARIO, "C", "x", clave_evento=clave)
    assert notificar(db, uno.asistente, TipoNotificacion.COMENTARIO, "C", "x", clave_evento=clave)


def test_sin_clave_de_evento_se_admiten_varias(db: Session, dos_gerentes: DosGerentes) -> None:
    gerente = dos_gerentes.uno.gerente
    notificar(db, gerente, TipoNotificacion.COMENTARIO, "C", "x")
    notificar(db, gerente, TipoNotificacion.COMENTARIO, "C", "x")
    assert total_de(db, gerente) == 2


def test_la_clave_de_evento_no_puede_estar_vacia(db: Session, dos_gerentes: DosGerentes) -> None:
    with pytest.raises(IntegrityError, match="ck_notificacion_clave_evento"):
        notificar(
            db, dos_gerentes.uno.gerente, TipoNotificacion.COMENTARIO, "C", "x", clave_evento=""
        )


def test_un_rollback_descarta_la_notificacion_y_su_evento(
    db: Session, dos_gerentes: DosGerentes, publicados: Publicados
) -> None:
    gerente = dos_gerentes.uno.gerente
    notificar(db, gerente, TipoNotificacion.DEUDA_CREADA, "Deuda", "x")
    db.rollback()
    db.commit()
    assert total_de(db, gerente) == 0
    assert publicados == []


def test_leida_se_deriva_de_leida_en(db: Session, dos_gerentes: DosGerentes) -> None:
    notificacion = notificar(db, dos_gerentes.uno.gerente, TipoNotificacion.VENCIDA, "V", "x")
    assert notificacion is not None
    assert NotificacionSalida.model_validate(notificacion).leida is False
    notificacion.leida_en = datetime.now(UTC)
    assert NotificacionSalida.model_validate(notificacion).leida is True
