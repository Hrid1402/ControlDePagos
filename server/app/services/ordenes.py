"""Órdenes urgentes del lado de la asistente (H19): pendientes, vista, aceptar y rechazar.

Ciclo de la orden (ck_orden_pago_estado): enviada -> vista -> aceptada o rechazada. TASK-63 crea,
cancela y reenvía; la validación del comprobante la deja pagada. Solo responde la asistente
destinataria: otra asistente del mismo gerente recibe 409 y otro gerente, 404.

Aceptar inicia el pago de la deuda en la misma transacción, con la orden como autorización de su
importe y moneda exactos (app/services/pagos.py). Rechazar solo cierra la orden y avisa al
gerente: la deuda queda libre para reenviar la orden o pagarla él (H18 CA09). Una orden aceptada
ya no se rechaza: el «no pude pagar» de una deuda en proceso es el reporte de TASK-71.

Las funciones no hacen commit: lo hace quien llama. Los eventos orden_* salen solo por
publicar_evento_orden, también los de TASK-63 (orden_nueva y orden_cancelada) y TASK-64
(orden_nueva al reenviar), siempre después del commit.

Orden de bloqueo: usuario -> orden_pago -> limite -> deuda, el de app/services/pagos.py. La
asistente se relee bloqueada antes que la orden: si la desactivan o le cierran la sesión mientras
responde, el traspaso de TASK-14 espera a que termine o la respuesta es 401.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from app.core.dependencias import Origen, gerente_de
from app.core.errores import ErrorApi
from app.core.eventos import Evento, TipoEvento, publicar_tras_commit
from app.core.tiempo import ahora_lima, zona_horaria
from app.models import Deuda, Empresa, OrdenPago, Servicio, Usuario
from app.schemas.ordenes import MotivoNoPago, OrdenAsistenteSalida
from app.services.auditoria import Accion, nombre_de, registrar_auditoria
from app.services.notificaciones import TipoNotificacion, notificar
from app.services.pagos import (
    AutorizacionOrden,
    InicioPago,
    ResultadoInicio,
    iniciar_pago,
    sin_permiso,
)

# Las que la asistente todavía debe responder: las que muestra la pantalla completa.
ESTADOS_PENDIENTES = ("enviada", "vista")
# motivo_rechazo guarda "codigo" o "codigo: detalle".
SEPARADOR_DETALLE = ": "

TEXTOS_MOTIVO = {
    MotivoNoPago.PORTAL_CAIDO: "el portal está caído",
    MotivoNoPago.SALDO_INSUFICIENTE: "no hay saldo suficiente",
    MotivoNoPago.MONTO_DISTINTO: "el monto es distinto",
    MotivoNoPago.AGENTE_CERRADO: "el agente está cerrado",
    MotivoNoPago.OTRO_MEDIO: "necesita otro medio de pago",
    MotivoNoPago.OTRO: "otro motivo",
}


@dataclass(frozen=True)
class RespuestaOrden:
    orden: OrdenPago
    repetido: bool


@dataclass(frozen=True)
class OrdenAceptada:
    orden: OrdenPago
    inicio: InicioPago
    repetido: bool


def version_de(orden: OrdenPago) -> str:
    """Cambia en cada transición y en cada reenvío de la misma orden."""
    return f"{orden.estado}:{orden.reenvios}"


def texto_motivo(motivo: MotivoNoPago, detalle: str | None) -> str:
    return f"{motivo.value}{SEPARADOR_DETALLE}{detalle}" if detalle else motivo.value


def leer_motivo(texto: str | None) -> tuple[MotivoNoPago | None, str | None]:
    """Separa motivo_rechazo en motivo y detalle. Un texto fuera del catálogo queda como
    detalle sin motivo."""
    if texto is None:
        return None, None
    codigo, _, detalle = texto.partition(SEPARADOR_DETALLE)
    try:
        return MotivoNoPago(codigo), detalle or None
    except ValueError:
        return None, texto


def empresa_de(db: Session, servicio: Servicio) -> str | None:
    if servicio.empresa_id is not None:
        return db.get_one(Empresa, servicio.empresa_id).nombre
    return servicio.empresa_nombre


def salida_orden(db: Session, orden: OrdenPago) -> OrdenAsistenteSalida:
    """La orden con los datos de su deuda que muestra la pantalla completa (H19 CA02)."""
    deuda = db.get_one(Deuda, orden.deuda_id)
    servicio = db.get_one(Servicio, deuda.servicio_id)
    motivo, detalle = leer_motivo(orden.motivo_rechazo)
    return OrdenAsistenteSalida(
        id=orden.id,
        deuda_id=orden.deuda_id,
        estado=orden.estado,
        version=version_de(orden),
        plazo=orden.plazo,
        mensaje=orden.mensaje,
        monto=orden.monto,
        moneda=orden.moneda,
        reenvios=orden.reenvios,
        vista_en=orden.vista_en,
        aceptada_en=orden.aceptada_en,
        creado_en=orden.creado_en,
        motivo=motivo,
        detalle=detalle,
        empresa=empresa_de(db, servicio),
        alias=servicio.alias,
        codigo_suministro=servicio.codigo_suministro,
        lugar_pago=servicio.lugar_pago,
        fecha_vencimiento=deuda.fecha_vencimiento,
        gerente_nombre=nombre_de(db.get_one(Usuario, orden.gerente_id)),
    )


def iso(valor: datetime | None) -> str | None:
    return valor.isoformat() if valor is not None else None


def publicar_evento_orden(db: Session, orden: OrdenPago, tipo: TipoEvento) -> None:
    """Único punto de publicación de los eventos orden_*. Se llama después de cambiar la orden y
    el evento sale solo si la transacción se confirma.

    - orden_nueva (TASK-63 al crear y reenviar, TASK-64 al reenviar): a la asistente, con la
      orden completa en datos.orden para mostrarla sin esperar a la API.
    - orden_cancelada (TASK-63): a la asistente. intento_vigente indica que la deuda sigue en
      proceso a su nombre: se cierra la pantalla completa, no la ventanilla.
    - orden_vista, orden_aceptada y orden_rechazada: al gerente, para su lista de órdenes, y a la
      asistente, para que sus otras pestañas cierren la pantalla completa.

    datos siempre trae orden_id, deuda_id, estado y version: el cliente descarta lo repetido.
    """
    datos: dict[str, Any] = {
        "orden_id": str(orden.id),
        "deuda_id": str(orden.deuda_id),
        "estado": orden.estado,
        "version": version_de(orden),
    }
    destinatarios: list[uuid.UUID | None] = [orden.gerente_id, orden.asistente_id]
    if tipo == TipoEvento.ORDEN_NUEVA:
        datos["orden"] = salida_orden(db, orden).model_dump(mode="json")
        destinatarios = [orden.asistente_id]
    elif tipo == TipoEvento.ORDEN_CANCELADA:
        deuda = db.get_one(Deuda, orden.deuda_id)
        datos["intento_vigente"] = (
            orden.asistente_id is not None
            and deuda.estado == "en_proceso"
            and deuda.pago_iniciado_por == orden.asistente_id
        )
        destinatarios = [orden.asistente_id]
    elif tipo == TipoEvento.ORDEN_VISTA:
        datos["vista_en"] = iso(orden.vista_en)
    elif tipo == TipoEvento.ORDEN_ACEPTADA:
        datos["aceptada_en"] = iso(orden.aceptada_en)
    elif tipo == TipoEvento.ORDEN_RECHAZADA:
        motivo, detalle = leer_motivo(orden.motivo_rechazo)
        datos |= {"motivo": motivo.value if motivo else None, "detalle": detalle}
    else:
        raise ValueError(f"{tipo} no es un evento de orden.")
    evento = Evento(tipo, datos)
    for usuario_id in destinatarios:
        if usuario_id is not None:
            publicar_tras_commit(db, usuario_id, evento)


def bloquear_asistente(db: Session, usuario: Usuario) -> None:
    """Relee la cuenta con FOR SHARE: la sesión se validó al recibir la solicitud y pudo
    desactivarse o revocarse antes de llegar aquí. Mientras dure la transacción, nadie la
    desactiva ni le traspasa las órdenes."""
    version = usuario.token_version
    vigente = db.scalar(
        select(Usuario)
        .where(Usuario.id == usuario.id)
        .with_for_update(read=True)
        .execution_options(populate_existing=True)
    )
    if vigente is None or vigente.eliminado_en is not None or vigente.estado != "activa":
        raise ErrorApi(401, "CUENTA_INACTIVA", "Tu cuenta no está activa.")
    if vigente.token_version != version:
        raise ErrorApi(401, "SESION_REVOCADA", "Tu sesión fue cerrada. Inicia sesión de nuevo.")


def bloquear_orden(db: Session, orden_id: uuid.UUID, gerente_id: uuid.UUID) -> OrdenPago:
    """Orden del gerente bloqueada hasta el commit; si no existe o es ajena, el mismo 404."""
    orden = db.scalar(
        select(OrdenPago)
        .where(OrdenPago.id == orden_id, OrdenPago.gerente_id == gerente_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if orden is None:
        raise ErrorApi(404, "NO_ENCONTRADO", "No se encontró el recurso solicitado.")
    return orden


def orden_de_la_asistente(db: Session, usuario: Usuario, orden_id: uuid.UUID) -> OrdenPago:
    gerente_id = gerente_de(usuario)
    if usuario.rol != "asistente" or gerente_id is None:
        raise sin_permiso()
    bloquear_asistente(db, usuario)
    orden = bloquear_orden(db, orden_id, gerente_id)
    if orden.asistente_id != usuario.id:
        raise ErrorApi(
            409, "ORDEN_DE_OTRA_ASISTENTE", "Esta orden ya no está asignada a tu cuenta."
        )
    return orden


def error_cerrada(orden: OrdenPago) -> ErrorApi:
    """La orden ya no admite respuesta. ORDEN_CANCELADA permite al cliente cerrar la pantalla
    con el aviso de H19 CA09."""
    if orden.estado == "cancelada":
        return ErrorApi(409, "ORDEN_CANCELADA", "El gerente canceló esta orden.")
    if orden.estado == "pagada":
        return ErrorApi(409, "ORDEN_CERRADA", "La orden ya está pagada.")
    return ErrorApi(409, "ORDEN_CERRADA", "Ya rechazaste esta orden.")


def consulta_pendientes(usuario: Usuario) -> Select[OrdenPago]:
    """Órdenes que la asistente aún debe responder, la más urgente primero (H19 CA06 y CA07).
    paginar agrega el id como desempate."""
    if usuario.rol != "asistente" or usuario.gerente_id is None:
        raise sin_permiso()
    return (
        select(OrdenPago)
        .where(
            OrdenPago.asistente_id == usuario.id,
            OrdenPago.gerente_id == usuario.gerente_id,
            OrdenPago.estado.in_(ESTADOS_PENDIENTES),
        )
        .order_by(OrdenPago.plazo.asc().nulls_last(), OrdenPago.creado_en)
    )


def marcar_vista(
    db: Session,
    usuario: Usuario,
    orden_id: uuid.UUID,
    *,
    origen: Origen,
    ahora: datetime | None = None,
) -> RespuestaOrden:
    """Registra que la asistente vio la orden: TASK-64 ya no la reenvía."""
    orden = orden_de_la_asistente(db, usuario, orden_id)
    if orden.estado in ("vista", "aceptada"):
        return RespuestaOrden(orden, repetido=True)
    if orden.estado != "enviada":
        raise error_cerrada(orden)
    orden.estado = "vista"
    orden.vista_en = ahora or ahora_lima()
    registrar_auditoria(
        db,
        usuario,
        Accion.ORDEN_VISTA,
        "orden_pago",
        orden.id,
        {"deuda_id": orden.deuda_id},
        origen=origen,
    )
    publicar_evento_orden(db, orden, TipoEvento.ORDEN_VISTA)
    return RespuestaOrden(orden, repetido=False)


def aceptar_orden(
    db: Session,
    usuario: Usuario,
    orden_id: uuid.UUID,
    *,
    origen: Origen,
    ahora: datetime | None = None,
) -> OrdenAceptada:
    """Acepta la orden e inicia el pago de su deuda en una sola transacción.

    Va en un savepoint: si la deuda no puede iniciarse, la orden vuelve a como estaba también en
    la sesión de quien llama. Aceptar de nuevo la misma orden repite el inicio: sin efectos si la
    deuda sigue en proceso a su nombre, o un inicio nuevo si ella lo canceló, porque la orden
    aceptada sigue autorizando el mismo importe.
    """
    momento = ahora or ahora_lima()
    with db.begin_nested():
        orden = orden_de_la_asistente(db, usuario, orden_id)
        anterior = orden.estado
        ya_aceptada = anterior == "aceptada"
        if not ya_aceptada:
            if anterior not in ESTADOS_PENDIENTES:
                raise error_cerrada(orden)
            orden.estado = "aceptada"
            orden.aceptada_en = momento
            orden.vista_en = orden.vista_en or momento
        inicio = iniciar_pago(
            db,
            usuario,
            orden.deuda_id,
            origen=origen,
            orden=AutorizacionOrden(orden),
            ahora=momento,
        )
        if inicio.resultado == ResultadoInicio.REQUIERE_APROBACION:
            # Solo ocurre si ella ya había pedido aprobar esta deuda: decide el gerente primero.
            raise ErrorApi(
                409,
                "APROBACION_PENDIENTE",
                "La deuda espera la decisión del gerente sobre tu solicitud de aprobación.",
            )
        if not ya_aceptada:
            registrar_auditoria(
                db,
                usuario,
                Accion.ORDEN_ACEPTADA,
                "orden_pago",
                orden.id,
                {
                    "deuda_id": orden.deuda_id,
                    "monto": orden.monto,
                    "moneda": orden.moneda,
                    "estado_anterior": anterior,
                },
                origen=origen,
            )
            publicar_evento_orden(db, orden, TipoEvento.ORDEN_ACEPTADA)
    return OrdenAceptada(orden, inicio, repetido=ya_aceptada and inicio.repetido)


def avisar_rechazo(
    db: Session,
    usuario: Usuario,
    orden: OrdenPago,
    motivo: MotivoNoPago,
    detalle: str | None,
    ahora: datetime,
) -> None:
    """Aviso al gerente con el motivo (H18 CA09). Urgente si la deuda vence hoy o ya venció
    (H28 CA05). La clave incluye los reenvíos: rechazar otra vez tras un reenvío vuelve a avisar."""
    gerente = db.get(Usuario, orden.gerente_id)
    if gerente is None:
        return
    deuda = db.get_one(Deuda, orden.deuda_id)
    servicio = db.get_one(Servicio, deuda.servicio_id)
    razon = detalle if motivo == MotivoNoPago.OTRO else TEXTOS_MOTIVO[motivo]
    if detalle and motivo != MotivoNoPago.OTRO:
        razon = f"{razon} ({detalle})"
    destino = empresa_de(db, servicio) or servicio.codigo_suministro
    notificar(
        db,
        gerente,
        TipoNotificacion.NO_PUDE_PAGAR,
        "Orden rechazada",
        f"{nombre_de(usuario)} no puede pagar {destino}: {razon}.",
        deuda_id=deuda.id,
        urgente=deuda.fecha_vencimiento <= ahora.astimezone(zona_horaria()).date(),
        clave_evento=f"orden_rechazada:{orden.id}:{orden.reenvios}",
        ahora=ahora,
    )


def rechazar_orden(
    db: Session,
    usuario: Usuario,
    orden_id: uuid.UUID,
    motivo: MotivoNoPago,
    detalle: str | None,
    *,
    origen: Origen,
    ahora: datetime | None = None,
) -> RespuestaOrden:
    """La asistente no puede cumplir la orden. La deuda no cambia: no estaba en proceso y no hay
    reserva que liberar. Repetir el rechazo no cambia el motivo ya registrado."""
    detalle = (detalle or "").strip() or None
    if motivo == MotivoNoPago.OTRO and detalle is None:
        raise ErrorApi(
            422, "VALIDACION", "Describe el motivo por el que no puedes pagar.", "detalle"
        )
    momento = ahora or ahora_lima()
    orden = orden_de_la_asistente(db, usuario, orden_id)
    if orden.estado == "rechazada":
        return RespuestaOrden(orden, repetido=True)
    if orden.estado == "aceptada":
        raise ErrorApi(
            409,
            "ORDEN_ACEPTADA",
            "Ya aceptaste esta orden. Si no pudiste pagar, repórtalo desde la deuda.",
        )
    if orden.estado not in ESTADOS_PENDIENTES:
        raise error_cerrada(orden)
    anterior = orden.estado
    orden.estado = "rechazada"
    orden.motivo_rechazo = texto_motivo(motivo, detalle)
    orden.vista_en = orden.vista_en or momento
    registrar_auditoria(
        db,
        usuario,
        Accion.ORDEN_RECHAZADA,
        "orden_pago",
        orden.id,
        {
            "deuda_id": orden.deuda_id,
            "motivo": motivo.value,
            "detalle": detalle,
            "estado_anterior": anterior,
        },
        origen=origen,
    )
    avisar_rechazo(db, usuario, orden, motivo, detalle, momento)
    publicar_evento_orden(db, orden, TipoEvento.ORDEN_RECHAZADA)
    return RespuestaOrden(orden, repetido=False)
