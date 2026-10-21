"""Deudas que se repiten cada mes y recibos retrasados (H11 CA04 y CA05, TASK-39).

Configuración: un servicio tiene a lo sumo una recurrencia (uq_recurrencia_servicio_id). Su tipo
sigue al de la categoría: monto_fijo para un servicio de monto fijo, variable para uno variable.

Generación (tarea diaria, app/workers/recurrencias.py): la deuda del mes M se crea cuando llega su
día de emisión en Lima (dia_emision, o el día 1 si no tiene). Vence el dia_vencimiento de M, o del
mes siguiente si ese día es anterior al de emisión. Un día que el mes no tiene (31 en febrero) se
ajusta al último día del mes.
- monto_fijo: pendiente, con el monto de la recurrencia.
- variable: esperando_recibo, sin monto, con fecha_estimada del recibo en su día de emisión. No se
  puede pagar hasta confirmar el importe (TASK-40).

Es idempotente y recupera días omitidos: recorre los meses desde el siguiente a ultima_generacion
(o desde el mes en que se configuró) hasta el actual y crea solo los que faltan. Si ya hay una
deuda del servicio en ese periodo, aunque esté anulada o se haya registrado a mano, no crea otra.
Un servicio dado de baja o una recurrencia inactiva no generan deudas; las pendientes se conservan.

Recibos retrasados: una deuda esperando_recibo cuya fecha estimada pasó hace más de DIAS_GRACIA
avisa al gerente y a su asistente, una sola vez por deuda (clave_evento).
"""

import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.dependencias import Origen
from app.core.errores import ErrorApi
from app.core.tiempo import ahora_lima, dia_del_mes, hoy_de, sumar_meses
from app.models import Categoria, Deuda, Recurrencia, Servicio, Usuario
from app.services.auditoria import Accion, diferencias, registrar_auditoria
from app.services.notificaciones import TipoNotificacion, notificar
from app.services.servicios import servicio_activo_propio, servicio_propio

DIAS_GRACIA = 3
TIPO_POR_CATEGORIA = {"monto_fijo": "monto_fijo", "servicio_variable": "variable"}


@dataclass(frozen=True)
class DatosRecurrencia:
    monto: Decimal | None
    moneda: str
    dia_emision: int | None
    dia_vencimiento: int
    activa: bool


def fechas_del_mes(recurrencia: Recurrencia, periodo: date) -> tuple[date, date]:
    """Día de emisión y vencimiento de la deuda del periodo."""
    emision = dia_del_mes(periodo.year, periodo.month, recurrencia.dia_emision or 1)
    vencimiento = dia_del_mes(periodo.year, periodo.month, recurrencia.dia_vencimiento)
    if vencimiento < emision:
        vencimiento = sumar_meses(periodo, 1, recurrencia.dia_vencimiento)
    return emision, vencimiento


def obtener_recurrencia(db: Session, servicio_id: uuid.UUID, gerente_id: uuid.UUID) -> Recurrencia:
    servicio_propio(db, servicio_id, gerente_id, campo="servicio_id")
    recurrencia = db.scalar(select(Recurrencia).where(Recurrencia.servicio_id == servicio_id))
    if recurrencia is None:
        raise ErrorApi(404, "NO_ENCONTRADO", "El servicio no tiene una deuda que se repita.")
    return recurrencia


def configurar_recurrencia(
    db: Session,
    usuario: Usuario,
    gerente_id: uuid.UUID,
    servicio_id: uuid.UUID,
    datos: DatosRecurrencia,
    *,
    origen: Origen,
) -> Recurrencia:
    """Crea o cambia la recurrencia del servicio. No hace commit."""
    servicio = servicio_activo_propio(db, servicio_id, gerente_id, bloquear=True)
    categoria = db.get(Categoria, servicio.categoria_id)
    tipo = TIPO_POR_CATEGORIA.get(categoria.tipo if categoria else "")
    if tipo is None:
        raise ErrorApi(
            422,
            "VALIDACION",
            "Solo los servicios de monto fijo o variable se repiten cada mes.",
            "servicio_id",
        )
    if tipo == "monto_fijo" and datos.monto is None:
        raise ErrorApi(422, "VALIDACION", "Escribe el monto que se paga cada mes.", "monto")
    recurrencia = db.scalar(
        select(Recurrencia).where(Recurrencia.servicio_id == servicio.id).with_for_update()
    )
    antes = (
        {
            "monto": recurrencia.monto,
            "moneda": recurrencia.moneda,
            "dia_emision": recurrencia.dia_emision,
            "dia_vencimiento": recurrencia.dia_vencimiento,
            "activa": recurrencia.activa,
        }
        if recurrencia
        else {}
    )
    if recurrencia is None:
        recurrencia = Recurrencia(servicio_id=servicio.id, tipo=tipo, dia_vencimiento=1)
        db.add(recurrencia)
    recurrencia.tipo = tipo
    # Una recurrencia variable no guarda monto: el de cada mes llega con su recibo.
    recurrencia.monto = datos.monto if tipo == "monto_fijo" else None
    recurrencia.moneda = datos.moneda
    recurrencia.dia_emision = datos.dia_emision
    recurrencia.dia_vencimiento = datos.dia_vencimiento
    recurrencia.activa = datos.activa
    db.flush()
    registrar_auditoria(
        db,
        usuario,
        Accion.SERVICIO_ACTUALIZADO,
        "servicio",
        servicio.id,
        {
            "recurrencia": diferencias(
                antes,
                {
                    "monto": recurrencia.monto,
                    "moneda": recurrencia.moneda,
                    "dia_emision": recurrencia.dia_emision,
                    "dia_vencimiento": recurrencia.dia_vencimiento,
                    "activa": recurrencia.activa,
                },
            )
        },
        origen=origen,
    )
    return recurrencia


def meses_pendientes(recurrencia: Recurrencia, hoy: date) -> list[date]:
    """Periodos sin generar cuya emisión ya llegó, en orden."""
    if recurrencia.ultima_generacion is not None:
        periodo = sumar_meses(recurrencia.ultima_generacion, 1, 1)
    else:
        creada = hoy_de(recurrencia.creado_en)
        periodo = creada.replace(day=1)
    meses = []
    while periodo <= hoy.replace(day=1):
        emision, _ = fechas_del_mes(recurrencia, periodo)
        if emision > hoy:
            break
        meses.append(periodo)
        periodo = sumar_meses(periodo, 1, 1)
    return meses


def generar_recurrentes(db: Session, ahora: datetime | None = None) -> int:
    """Crea las deudas de las recurrencias activas que faltan hasta hoy. Devuelve cuántas creó."""
    hoy = hoy_de(ahora or ahora_lima())
    filas = db.execute(
        select(Recurrencia, Servicio)
        .join(Servicio, Servicio.id == Recurrencia.servicio_id)
        .where(Recurrencia.activa, Servicio.estado == "activo", Servicio.eliminado_en.is_(None))
        .order_by(Recurrencia.id)
        .with_for_update(of=Recurrencia, skip_locked=True)
    ).all()
    creadas = 0
    for recurrencia, servicio in filas:
        for periodo in meses_pendientes(recurrencia, hoy):
            existe = db.scalar(
                select(Deuda.id).where(
                    Deuda.servicio_id == servicio.id,
                    Deuda.periodo == periodo,
                    Deuda.cuota_numero.is_(None),
                )
            )
            if existe is None:
                emision, vencimiento = fechas_del_mes(recurrencia, periodo)
                fijo = recurrencia.tipo == "monto_fijo"
                db.add(
                    Deuda(
                        gerente_id=servicio.gerente_id,
                        servicio_id=servicio.id,
                        periodo=periodo,
                        monto=recurrencia.monto if fijo else None,
                        moneda=recurrencia.moneda,
                        fecha_emision=emision if fijo else None,
                        fecha_estimada=None if fijo else emision,
                        fecha_vencimiento=vencimiento,
                        estado="pendiente" if fijo else "esperando_recibo",
                        origen="recurrente",
                    )
                )
                creadas += 1
            recurrencia.ultima_generacion = periodo
        db.flush()
    return creadas


def avisar_recibos_retrasados(db: Session, ahora: datetime | None = None) -> int:
    """Avisa de cada recibo que no llega pasados DIAS_GRACIA de su fecha estimada."""
    momento = ahora or ahora_lima()
    limite = hoy_de(momento) - timedelta(days=DIAS_GRACIA)
    filas = db.execute(
        select(Deuda, Servicio)
        .join(Servicio, Servicio.id == Deuda.servicio_id)
        .where(Deuda.estado == "esperando_recibo", Deuda.fecha_estimada < limite)
    ).all()
    avisos = 0
    for deuda, servicio in filas:
        nombre = servicio.alias or servicio.empresa_nombre or "un servicio"
        destinatarios = db.scalars(
            select(Usuario).where(
                (Usuario.id == deuda.gerente_id)
                | ((Usuario.gerente_id == deuda.gerente_id) & (Usuario.rol == "asistente"))
            )
        )
        for usuario in destinatarios:
            # Sin tipo propio en el esquema: el recibo retrasado avisa como un vencimiento cercano.
            enviado = notificar(
                db,
                usuario,
                TipoNotificacion.POR_VENCER,
                "El recibo se retrasa",
                f"El recibo de {nombre} no llega y vence el "
                f"{deuda.fecha_vencimiento:%d/%m/%Y}. Revisa con la empresa o registra el monto.",
                deuda_id=deuda.id,
                clave_evento=f"recibo_retrasado:{deuda.id}",
                ahora=momento,
            )
            avisos += enviado is not None
    return avisos
