import uuid
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from functools import partial

import pytest
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.core.dependencias import Origen
from app.core.errores import ErrorApi
from app.core.eventos import Evento, TipoEvento
from app.models import Auditoria, Deuda, Limite, Notificacion, OrdenPago, Usuario
from app.schemas.ordenes import MotivoNoPago
from app.services.ordenes import (
    aceptar_orden,
    leer_motivo,
    marcar_vista,
    rechazar_orden,
    salida_orden,
)
from app.services.pagos import ResultadoInicio, cancelar_inicio, iniciar_pago
from tests.conftest import (
    DosGerentes,
    Equipo,
    en_proceso_por,
    nueva_deuda,
    nueva_orden,
    nuevo_comprobante,
)

Publicados = list[tuple[uuid.UUID, Evento]]

ORIGEN = Origen(dispositivo="pruebas", ip=None)
AHORA = datetime(2026, 10, 19, 17, 0, tzinfo=UTC)  # 19/10 12:00 en Lima


def error_de(accion: Callable[[], object]) -> ErrorApi:
    with pytest.raises(ErrorApi) as info:
        accion()
    return info.value


def orden_de(db: Session, equipo: Equipo, estado: str = "enviada", **opciones: str) -> OrdenPago:
    deuda = nueva_deuda(db, equipo.gerente, **opciones)
    return nueva_orden(db, deuda, estado=estado, asistente=equipo.asistente)


def ver(db: Session, usuario: Usuario, orden: OrdenPago) -> bool:
    return marcar_vista(db, usuario, orden.id, origen=ORIGEN, ahora=AHORA).repetido


def aceptar(db: Session, usuario: Usuario, orden: OrdenPago) -> bool:
    return aceptar_orden(db, usuario, orden.id, origen=ORIGEN, ahora=AHORA).repetido


def rechazar(
    db: Session,
    usuario: Usuario,
    orden: OrdenPago,
    motivo: MotivoNoPago = MotivoNoPago.SALDO_INSUFICIENTE,
    detalle: str | None = None,
) -> bool:
    return rechazar_orden(
        db, usuario, orden.id, motivo, detalle, origen=ORIGEN, ahora=AHORA
    ).repetido


def auditorias(db: Session, entidad_id: uuid.UUID, accion: str) -> list[Auditoria]:
    return list(
        db.scalars(
            select(Auditoria).where(Auditoria.entidad_id == entidad_id, Auditoria.accion == accion)
        )
    )


def avisos(db: Session, usuario: Usuario) -> list[Notificacion]:
    return list(db.scalars(select(Notificacion).where(Notificacion.usuario_id == usuario.id)))


def tipos(publicados: Publicados) -> list[tuple[uuid.UUID, str]]:
    return [(usuario_id, evento.tipo) for usuario_id, evento in publicados]


# Vista


def test_ver_la_orden_la_marca_vista_y_avisa_tras_el_commit(
    db: Session, dos_gerentes: DosGerentes, publicados: Publicados
) -> None:
    equipo = dos_gerentes.uno
    orden = orden_de(db, equipo)

    assert ver(db, equipo.asistente, orden) is False

    assert (orden.estado, orden.vista_en) == ("vista", AHORA)
    assert len(auditorias(db, orden.id, "orden_vista")) == 1
    assert publicados == []
    db.commit()
    assert tipos(publicados) == [
        (equipo.gerente.id, TipoEvento.ORDEN_VISTA),
        (equipo.asistente.id, TipoEvento.ORDEN_VISTA),
    ]
    datos = publicados[0][1].datos
    assert (datos["orden_id"], datos["version"]) == (str(orden.id), "vista:0")


@pytest.mark.parametrize("estado", ["vista", "aceptada"])
def test_ver_de_nuevo_no_tiene_efectos(
    db: Session, dos_gerentes: DosGerentes, publicados: Publicados, estado: str
) -> None:
    equipo = dos_gerentes.uno
    orden = orden_de(db, equipo, estado)

    assert ver(db, equipo.asistente, orden) is True

    assert orden.estado == estado
    assert auditorias(db, orden.id, "orden_vista") == []
    db.commit()
    assert publicados == []


@pytest.mark.parametrize(
    ("estado", "codigo"),
    [("cancelada", "ORDEN_CANCELADA"), ("rechazada", "ORDEN_CERRADA"), ("pagada", "ORDEN_CERRADA")],
)
def test_ver_una_orden_cerrada_responde_409(
    db: Session, dos_gerentes: DosGerentes, estado: str, codigo: str
) -> None:
    equipo = dos_gerentes.uno
    orden = orden_de(db, equipo, estado)

    error = error_de(lambda: ver(db, equipo.asistente, orden))

    assert (error.status_code, error.code) == (409, codigo)


# Aceptar


def test_aceptar_inicia_el_pago_en_la_misma_transaccion(
    db: Session, dos_gerentes: DosGerentes, publicados: Publicados
) -> None:
    equipo = dos_gerentes.uno
    # La orden autoriza aunque supere el límite del gerente (H18 CA08).
    db.add(Limite(gerente_id=equipo.gerente.id, por_pago=Decimal("10.00")))
    orden = orden_de(db, equipo, monto="100.00")

    aceptada = aceptar_orden(db, equipo.asistente, orden.id, origen=ORIGEN, ahora=AHORA)

    assert (aceptada.repetido, aceptada.inicio.resultado) == (False, ResultadoInicio.INICIADO)
    assert (orden.estado, orden.aceptada_en, orden.vista_en) == ("aceptada", AHORA, AHORA)
    deuda = db.get_one(Deuda, orden.deuda_id)
    assert (deuda.estado, deuda.pago_iniciado_por) == ("en_proceso", equipo.asistente.id)
    [registro] = auditorias(db, orden.id, "orden_aceptada")
    assert registro.detalle == {
        "deuda_id": str(deuda.id),
        "monto": "100.00",
        "moneda": "PEN",
        "estado_anterior": "enviada",
    }
    [inicio] = auditorias(db, deuda.id, "pago_iniciado")
    assert (inicio.detalle["autorizacion"], inicio.detalle["orden_id"]) == ("orden", str(orden.id))
    assert publicados == []
    db.commit()
    assert tipos(publicados) == [
        (equipo.gerente.id, TipoEvento.ORDEN_ACEPTADA),
        (equipo.asistente.id, TipoEvento.ORDEN_ACEPTADA),
    ]


def test_aceptar_una_orden_vista_conserva_cuando_se_vio(
    db: Session, dos_gerentes: DosGerentes
) -> None:
    equipo = dos_gerentes.uno
    orden = orden_de(db, equipo)
    vista_en = AHORA - timedelta(minutes=5)
    orden.estado, orden.vista_en = "vista", vista_en

    aceptar(db, equipo.asistente, orden)

    assert (orden.estado, orden.vista_en) == ("aceptada", vista_en)


def test_aceptar_dos_veces_no_repite_efectos(
    db: Session, dos_gerentes: DosGerentes, publicados: Publicados
) -> None:
    equipo = dos_gerentes.uno
    orden = orden_de(db, equipo)
    aceptar(db, equipo.asistente, orden)
    db.commit()
    publicados.clear()

    assert aceptar(db, equipo.asistente, orden) is True

    db.commit()
    assert publicados == []
    assert len(auditorias(db, orden.id, "orden_aceptada")) == 1
    assert len(auditorias(db, orden.deuda_id, "pago_iniciado")) == 1


def test_aceptar_tras_cancelar_el_inicio_vuelve_a_iniciar(
    db: Session, dos_gerentes: DosGerentes
) -> None:
    equipo = dos_gerentes.uno
    orden = orden_de(db, equipo)
    aceptar(db, equipo.asistente, orden)
    cancelar_inicio(db, equipo.asistente, orden.deuda_id, None, origen=ORIGEN)
    assert orden.estado == "aceptada"

    assert aceptar(db, equipo.asistente, orden) is False

    assert db.get_one(Deuda, orden.deuda_id).estado == "en_proceso"
    assert len(auditorias(db, orden.id, "orden_aceptada")) == 1
    assert len(auditorias(db, orden.deuda_id, "pago_iniciado")) == 2


@pytest.mark.parametrize("cambio", ["monto", "moneda", "abono"])
def test_aceptar_con_la_deuda_cambiada_responde_409_y_no_cambia_nada(
    db: Session, dos_gerentes: DosGerentes, publicados: Publicados, cambio: str
) -> None:
    equipo = dos_gerentes.uno
    orden = orden_de(db, equipo, monto="100.00")
    deuda = db.get_one(Deuda, orden.deuda_id)
    # Cambios posteriores a la orden: ya no es el importe ni la moneda que autorizó el gerente.
    if cambio == "monto":
        deuda.monto = Decimal("120.00")
    if cambio == "moneda":
        deuda.moneda = "USD"
    if cambio == "abono":
        nuevo_comprobante(db, deuda, equipo.gerente, "30.00")
        deuda.estado = "pagada_parcial"
    db.flush()
    estado_deuda = deuda.estado

    error = error_de(lambda: aceptar(db, equipo.asistente, orden))

    assert (error.status_code, error.code) == (409, "ORDEN_NO_VALIDA")
    db.expire_all()
    assert (orden.estado, orden.aceptada_en, orden.vista_en) == ("enviada", None, None)
    assert (deuda.estado, deuda.pago_iniciado_por, deuda.pago_iniciado_en) == (
        estado_deuda,
        None,
        None,
    )
    assert auditorias(db, orden.id, "orden_aceptada") == []
    assert auditorias(db, deuda.id, "pago_iniciado") == []
    db.commit()
    assert publicados == []


def test_aceptar_con_aprobacion_pendiente_responde_409_y_deshace_todo(
    db: Session, dos_gerentes: DosGerentes, publicados: Publicados
) -> None:
    equipo = dos_gerentes.uno
    db.add(Limite(gerente_id=equipo.gerente.id, por_pago=Decimal("10.00")))
    deuda = nueva_deuda(db, equipo.gerente)
    pedido = iniciar_pago(db, equipo.asistente, deuda.id, origen=ORIGEN, ahora=AHORA)
    assert pedido.resultado == ResultadoInicio.REQUIERE_APROBACION
    db.commit()
    publicados.clear()
    orden = nueva_orden(db, deuda, asistente=equipo.asistente)

    error = error_de(lambda: aceptar(db, equipo.asistente, orden))

    assert (error.status_code, error.code) == (409, "APROBACION_PENDIENTE")
    db.expire_all()
    assert orden.estado == "enviada"
    assert deuda.estado == "esperando_aprobacion"
    db.commit()
    assert publicados == []


def test_aceptar_una_deuda_que_paga_otra_persona_responde_409(
    db: Session, dos_gerentes: DosGerentes
) -> None:
    equipo = dos_gerentes.uno
    orden = orden_de(db, equipo)
    en_proceso_por(db, db.get_one(Deuda, orden.deuda_id), equipo.gerente)

    error = error_de(lambda: aceptar(db, equipo.asistente, orden))

    assert (error.status_code, error.code) == (409, "PAGO_EN_CURSO")
    db.expire_all()
    assert orden.estado == "enviada"


@pytest.mark.parametrize(
    ("estado", "codigo"),
    [("cancelada", "ORDEN_CANCELADA"), ("rechazada", "ORDEN_CERRADA"), ("pagada", "ORDEN_CERRADA")],
)
def test_aceptar_una_orden_cerrada_responde_409(
    db: Session, dos_gerentes: DosGerentes, estado: str, codigo: str
) -> None:
    equipo = dos_gerentes.uno
    orden = orden_de(db, equipo, estado)

    error = error_de(lambda: aceptar(db, equipo.asistente, orden))

    assert (error.status_code, error.code) == (409, codigo)
    assert db.get_one(Deuda, orden.deuda_id).estado == "pendiente"


def test_aceptar_despues_del_plazo_esta_permitido(db: Session, dos_gerentes: DosGerentes) -> None:
    equipo = dos_gerentes.uno
    deuda = nueva_deuda(db, equipo.gerente)
    orden = nueva_orden(db, deuda, plazo=AHORA - timedelta(hours=1), asistente=equipo.asistente)

    aceptar(db, equipo.asistente, orden)

    assert orden.estado == "aceptada"


@pytest.mark.parametrize(
    ("cambio", "codigo"),
    [
        ("UPDATE usuario SET estado = 'inactiva' WHERE id = :id", "CUENTA_INACTIVA"),
        ("UPDATE usuario SET eliminado_en = now() WHERE id = :id", "CUENTA_INACTIVA"),
        ("UPDATE usuario SET token_version = token_version + 1 WHERE id = :id", "SESION_REVOCADA"),
    ],
)
def test_asistente_desactivada_a_mitad_del_flujo_recibe_401(
    db: Session, dos_gerentes: DosGerentes, cambio: str, codigo: str
) -> None:
    equipo = dos_gerentes.uno
    orden = orden_de(db, equipo)
    # La sesión ya se validó (el usuario cargado sigue activo); la cuenta cambia después en la
    # base, como al desactivarla desde otra solicitud.
    db.execute(text(cambio), {"id": equipo.asistente.id})

    error = error_de(lambda: aceptar(db, equipo.asistente, orden))

    assert (error.status_code, error.code) == (401, codigo)
    db.expire_all()
    assert orden.estado == "enviada"
    assert db.get_one(Deuda, orden.deuda_id).estado == "pendiente"


# Quién puede responder


def test_otra_asistente_del_mismo_gerente_recibe_409(
    db: Session, dos_gerentes: DosGerentes
) -> None:
    equipo = dos_gerentes.uno
    orden = orden_de(db, equipo)
    equipo.asistente.estado = "inactiva"
    db.flush()
    nueva = Usuario(
        rol="asistente", gerente_id=equipo.gerente.id, username="asistente_nueva", password_hash="x"
    )
    db.add(nueva)
    db.flush()

    for accion in (ver, aceptar, rechazar):
        error = error_de(partial(accion, db, nueva, orden))
        assert (error.status_code, error.code) == (409, "ORDEN_DE_OTRA_ASISTENTE")
    db.expire_all()
    assert orden.estado == "enviada"


def test_orden_de_otro_gerente_responde_404(db: Session, dos_gerentes: DosGerentes) -> None:
    orden = orden_de(db, dos_gerentes.dos)

    for accion in (ver, aceptar, rechazar):
        error = error_de(partial(accion, db, dos_gerentes.uno.asistente, orden))
        assert (error.status_code, error.code) == (404, "NO_ENCONTRADO")


def test_el_gerente_no_responde_ordenes(db: Session, dos_gerentes: DosGerentes) -> None:
    equipo = dos_gerentes.uno
    orden = orden_de(db, equipo)

    error = error_de(lambda: aceptar(db, equipo.gerente, orden))

    assert (error.status_code, error.code) == (403, "SIN_PERMISO")


# Rechazar


def test_rechazar_cierra_la_orden_y_avisa_al_gerente(
    db: Session, dos_gerentes: DosGerentes, publicados: Publicados
) -> None:
    equipo = dos_gerentes.uno
    orden = orden_de(db, equipo)

    assert rechazar(db, equipo.asistente, orden, detalle="  solo tengo 50  ") is False

    assert orden.estado == "rechazada"
    assert orden.motivo_rechazo == "saldo_insuficiente: solo tengo 50"
    assert orden.vista_en == AHORA
    deuda = db.get_one(Deuda, orden.deuda_id)
    assert (deuda.estado, deuda.pago_iniciado_por) == ("pendiente", None)
    [registro] = auditorias(db, orden.id, "orden_rechazada")
    assert registro.detalle == {
        "deuda_id": str(deuda.id),
        "motivo": "saldo_insuficiente",
        "detalle": "solo tengo 50",
        "estado_anterior": "enviada",
    }
    [aviso] = avisos(db, equipo.gerente)
    assert (aviso.tipo, aviso.urgente, aviso.deuda_id) == ("no_pude_pagar", False, deuda.id)
    assert aviso.clave_evento == f"orden_rechazada:{orden.id}:0"
    assert "no hay saldo suficiente (solo tengo 50)" in aviso.mensaje
    db.commit()
    assert tipos(publicados) == [
        (equipo.gerente.id, TipoEvento.NOTIFICACION),
        (equipo.gerente.id, TipoEvento.ORDEN_RECHAZADA),
        (equipo.asistente.id, TipoEvento.ORDEN_RECHAZADA),
    ]
    datos = publicados[1][1].datos
    assert (datos["motivo"], datos["detalle"]) == ("saldo_insuficiente", "solo tengo 50")


def test_rechazo_es_urgente_si_la_deuda_vence_hoy(db: Session, dos_gerentes: DosGerentes) -> None:
    equipo = dos_gerentes.uno
    orden = orden_de(db, equipo)
    db.get_one(Deuda, orden.deuda_id).fecha_vencimiento = date(2026, 10, 19)

    rechazar(db, equipo.asistente, orden, MotivoNoPago.OTRO, "El cajero no funciona")

    [aviso] = avisos(db, equipo.gerente)
    assert aviso.urgente is True
    assert aviso.mensaje.endswith(": El cajero no funciona.")
    assert orden.motivo_rechazo == "otro: El cajero no funciona"


@pytest.mark.parametrize("detalle", [None, "", "   "])
def test_motivo_otro_exige_detalle(
    db: Session, dos_gerentes: DosGerentes, detalle: str | None
) -> None:
    equipo = dos_gerentes.uno
    orden = orden_de(db, equipo)

    error = error_de(lambda: rechazar(db, equipo.asistente, orden, MotivoNoPago.OTRO, detalle))

    assert (error.status_code, error.code, error.field) == (422, "VALIDACION", "detalle")
    assert orden.estado == "enviada"


def test_rechazar_de_nuevo_no_cambia_el_motivo_ni_avisa_otra_vez(
    db: Session, dos_gerentes: DosGerentes, publicados: Publicados
) -> None:
    equipo = dos_gerentes.uno
    orden = orden_de(db, equipo)
    rechazar(db, equipo.asistente, orden, MotivoNoPago.PORTAL_CAIDO)
    db.commit()
    publicados.clear()

    assert rechazar(db, equipo.asistente, orden, MotivoNoPago.AGENTE_CERRADO) is True

    assert orden.motivo_rechazo == "portal_caido"
    assert len(avisos(db, equipo.gerente)) == 1
    assert len(auditorias(db, orden.id, "orden_rechazada")) == 1
    db.commit()
    assert publicados == []


def test_rechazar_tras_un_reenvio_vuelve_a_avisar(db: Session, dos_gerentes: DosGerentes) -> None:
    equipo = dos_gerentes.uno
    orden = orden_de(db, equipo)
    rechazar(db, equipo.asistente, orden)
    # Reenvío de TASK-63 sobre la misma orden.
    orden.estado, orden.reenvios = "enviada", 1
    db.flush()

    rechazar(db, equipo.asistente, orden)

    assert [a.clave_evento for a in avisos(db, equipo.gerente)] == [
        f"orden_rechazada:{orden.id}:0",
        f"orden_rechazada:{orden.id}:1",
    ]


def test_rechazar_una_orden_aceptada_responde_409(db: Session, dos_gerentes: DosGerentes) -> None:
    equipo = dos_gerentes.uno
    orden = orden_de(db, equipo)
    aceptar(db, equipo.asistente, orden)

    error = error_de(lambda: rechazar(db, equipo.asistente, orden))

    assert (error.status_code, error.code) == (409, "ORDEN_ACEPTADA")
    assert orden.estado == "aceptada"
    assert db.get_one(Deuda, orden.deuda_id).estado == "en_proceso"


@pytest.mark.parametrize(
    ("estado", "codigo"), [("cancelada", "ORDEN_CANCELADA"), ("pagada", "ORDEN_CERRADA")]
)
def test_rechazar_una_orden_cerrada_responde_409(
    db: Session, dos_gerentes: DosGerentes, estado: str, codigo: str
) -> None:
    equipo = dos_gerentes.uno
    orden = orden_de(db, equipo, estado)

    error = error_de(lambda: rechazar(db, equipo.asistente, orden))

    assert (error.status_code, error.code) == (409, codigo)
    assert avisos(db, equipo.gerente) == []


# Salida


def test_salida_con_los_datos_de_la_pantalla_completa(
    db: Session, dos_gerentes: DosGerentes
) -> None:
    equipo = dos_gerentes.uno
    equipo.gerente.nombres, equipo.gerente.apellidos = "Ana", "Ruiz"
    orden = orden_de(db, equipo, monto="85.40", moneda="USD")
    orden.mensaje = "Hoy antes de las 5"
    orden.motivo_rechazo = "monto_distinto: el recibo dice 90"

    salida = salida_orden(db, orden)

    assert (salida.monto, salida.moneda, salida.mensaje) == (
        Decimal("85.40"),
        "USD",
        "Hoy antes de las 5",
    )
    assert (salida.empresa, salida.gerente_nombre, salida.version) == (
        "Hidrandina",
        "Ana Ruiz",
        "enviada:0",
    )
    assert (salida.motivo, salida.detalle) == (MotivoNoPago.MONTO_DISTINTO, "el recibo dice 90")


@pytest.mark.parametrize(
    ("texto", "esperado"),
    [
        (None, (None, None)),
        ("portal_caido", (MotivoNoPago.PORTAL_CAIDO, None)),
        ("otro: sin luz: todo el día", (MotivoNoPago.OTRO, "sin luz: todo el día")),
        ("texto libre anterior", (None, "texto libre anterior")),
    ],
)
def test_leer_motivo(texto: str | None, esperado: tuple[MotivoNoPago | None, str | None]) -> None:
    assert leer_motivo(texto) == esperado


def test_aceptar_una_orden_no_se_afecta_por_otra_deuda_esperando_recibo(
    db: Session, dos_gerentes: DosGerentes
) -> None:
    equipo = dos_gerentes.uno
    sin_monto = nueva_deuda(db, equipo.gerente, monto=None, estado="esperando_recibo")
    orden = orden_de(db, equipo, monto="100.00")

    aceptada = aceptar_orden(db, equipo.asistente, orden.id, origen=ORIGEN, ahora=AHORA)

    assert aceptada.inicio.resultado == ResultadoInicio.INICIADO
    assert db.get_one(Deuda, orden.deuda_id).estado == "en_proceso"
    assert (sin_monto.estado, sin_monto.monto) == ("esperando_recibo", None)
