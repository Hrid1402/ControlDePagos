"""Registro manual de deudas (H11, TASK-38): CA01 a CA03 y CA09.

Periodo: si no se indica, es el mes del vencimiento, guardado como su primer día. Un vencimiento
del 31 de enero pertenece a enero, no a febrero.

Vencida (CA02): el vencimiento es anterior a hoy en Lima. Se informa en la respuesta y no
impide el registro; tampoco se guarda, porque vencida es un dato calculado. Una deuda que vence
hoy todavía no está vencida, igual que en la bandeja.

Duplicado (CA03): uq_deuda_periodo admite una sola deuda no anulada por servicio, periodo y
cuota. El registro manual no tiene cuota, que el índice cuenta como 0; las cuotas de préstamo
son mayores que 0 (ck_deuda_cuota_numero) y no chocan con ella. Un duplicado responde 409 con la
deuda existente, que siempre es del mismo gerente porque el servicio lo es. No hay confirmación
que permita saltar el índice. Una deuda anulada no ocupa el periodo.

Concurrencia: el servicio se bloquea hasta el commit. Dos registros del mismo servicio se turnan
y el segundo ve la deuda del primero; un registro y una baja simultáneos también se turnan, así
que no queda una deuda nueva en un servicio de baja. Una deuda que otro proceso inserta sin
bloquear el servicio (la generación de recurrentes) también hace esperar, porque su llave
foránea toma FOR KEY SHARE sobre el servicio. Si aun así el índice rechaza la inserción, se
responde el mismo 409.
"""

import uuid
from dataclasses import dataclass
from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.dependencias import Origen
from app.core.errores import ErrorApi
from app.core.tiempo import ahora_lima
from app.models import Deuda, Usuario
from app.schemas.deudas import DeudaEntrada, DeudaExistente
from app.services.auditoria import Accion, nombre_de, registrar_auditoria
from app.services.bandeja import hoy_de
from app.services.notificaciones import TipoNotificacion, notificar
from app.services.servicios import fila_de, servicio_activo_propio


@dataclass(frozen=True)
class Registro:
    deuda: Deuda
    vencida: bool


def periodo_de(texto: str | None, fecha_vencimiento: date) -> date:
    """Primer día del periodo AAAA-MM indicado o, si se omite, del mes del vencimiento."""
    if texto is None:
        return fecha_vencimiento.replace(day=1)
    return date(int(texto[:4]), int(texto[5:7]), 1)


def texto_periodo(periodo: date) -> str:
    return periodo.strftime("%Y-%m")


def deuda_activa_del_periodo(db: Session, servicio_id: uuid.UUID, periodo: date) -> Deuda | None:
    """La deuda sin cuota que ocupa el servicio y el periodo en uq_deuda_periodo."""
    return db.scalar(
        select(Deuda).where(
            Deuda.servicio_id == servicio_id,
            Deuda.periodo == periodo,
            Deuda.cuota_numero.is_(None),
            Deuda.estado != "anulada",
        )
    )


def duplicado(existente: Deuda | None) -> ErrorApi:
    datos = None
    if existente is not None:
        referencia = DeudaExistente(
            id=existente.id,
            periodo=texto_periodo(existente.periodo),
            estado=existente.estado,
            monto=existente.monto,
            moneda=existente.moneda,
            fecha_vencimiento=existente.fecha_vencimiento,
        )
        datos = {"deuda_existente": referencia.model_dump(mode="json")}
    return ErrorApi(
        409,
        "DUPLICADO",
        "Ya existe una deuda de este servicio para ese periodo.",
        "periodo",
        datos=datos,
    )


def registrar_deuda(
    db: Session,
    usuario: Usuario,
    gerente_id: uuid.UUID,
    datos: DeudaEntrada,
    origen: Origen,
    ahora: datetime | None = None,
) -> Registro:
    """Gerente o asistente registran la deuda del mes de un servicio activo propio. Si la
    registra la asistente, se avisa al gerente. No hace commit."""
    servicio = servicio_activo_propio(
        db, datos.servicio_id, gerente_id, bloquear=True, campo="servicio_id"
    )
    periodo = periodo_de(datos.periodo, datos.fecha_vencimiento)
    existente = deuda_activa_del_periodo(db, servicio.id, periodo)
    if existente is not None:
        raise duplicado(existente)
    deuda = Deuda(
        gerente_id=gerente_id,
        servicio_id=servicio.id,
        periodo=periodo,
        monto=datos.monto,
        moneda=datos.moneda,
        fecha_vencimiento=datos.fecha_vencimiento,
        numero_recibo=datos.numero_recibo,
        estado="pendiente",
        origen="manual",
        creado_por=usuario.id,
    )
    try:
        with db.begin_nested():
            db.add(deuda)
            db.flush()
    except IntegrityError as error:
        if "uq_deuda_periodo" not in str(error.orig):
            raise
        # La otra deuda ya está confirmada: el índice esperó su commit para rechazar esta.
        raise duplicado(deuda_activa_del_periodo(db, servicio.id, periodo)) from None
    db.refresh(deuda)
    vencida = deuda.fecha_vencimiento < hoy_de(ahora or ahora_lima())
    registrar_auditoria(
        db,
        usuario,
        Accion.DEUDA_CREADA,
        "deuda",
        deuda.id,
        {
            "servicio_id": servicio.id,
            "periodo": texto_periodo(deuda.periodo),
            "monto": deuda.monto,
            "moneda": deuda.moneda,
            "fecha_vencimiento": deuda.fecha_vencimiento,
            "numero_recibo": deuda.numero_recibo,
            "vencida": vencida,
        },
        origen=origen,
    )
    if usuario.rol == "asistente":
        gerente = db.get(Usuario, gerente_id)
        if gerente is not None:
            nombre = servicio.alias or fila_de(db, servicio).nombre_empresa
            notificar(
                db,
                gerente,
                TipoNotificacion.DEUDA_CREADA,
                "Deuda registrada",
                f"{nombre_de(usuario)} registró la deuda de {nombre} por {deuda.moneda} "
                f"{deuda.monto}, con vencimiento el {deuda.fecha_vencimiento:%d/%m/%Y}.",
                deuda_id=deuda.id,
                clave_evento=f"deuda_creada:{deuda.id}",
                ahora=ahora,
            )
    return Registro(deuda, vencida)
