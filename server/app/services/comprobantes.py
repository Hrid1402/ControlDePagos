"""Subida, reemplazo y consulta de comprobantes (H24 CA01, CA06 y CA08; TASK-84 y TASK-109).

Reglas al subir, todas con las deudas bloqueadas hasta el commit:
- Las deudas son del gerente y comparten moneda, que pasa a ser la del comprobante. El OCR
  comprueba después que el documento diga lo mismo.
- Solo la asistente sube el voucher, sobre un intento vigente: en_proceso o por_validar (otro
  comprobante del mismo pago). El gerente ya no adjunta (reemplaza CA09, TASK-109): valida.
- monto_aplicado de cada deuda no supera lo disponible: el saldo menos lo que ya reservan otros
  comprobantes que todavía pueden validarse. Si se omite, se aplica todo lo disponible.
- Un archivo con el mismo hash que un comprobante no rechazado responde 409 DUPLICADO. Si es del
  mismo gerente, indica en qué deudas se usó; si es ajeno, el mensaje es genérico (contrato H24,
  punto 5).
- El archivo se guarda antes de insertar. Si la inserción falla se borra aquí, y si falla el
  commit lo borra confirmar_con_archivo: no quedan archivos huérfanos.
- Las deudas pasan a por_validar hasta que el comprobante se resuelve.
- La validación automática (OCR) se encola en la cola ocr solo si la subida se confirma
  (app/workers/comprobantes.py). Si no se pudo encolar, la recupera su revisión programada.

Reemplazo (CA08): un comprobante rechazado se reemplaza por otro nuevo con reemplaza_a_id, con
el mismo reparto y las mismas reglas; el rechazado se conserva como historial.

Las funciones no hacen commit: lo hace la ruta con confirmar_con_archivo.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.dependencias import Origen
from app.core.errores import ErrorApi
from app.core.tiempo import ahora_lima
from app.models import Comprobante, ComprobanteDeuda, Deuda, Usuario
from app.schemas.comprobantes import RepartoComprobanteEntrada
from app.services.archivos import (
    ArchivoValidado,
    eliminar_privado,
    guardar_privado,
    ruta_comprobante,
)
from app.services.auditoria import Accion, registrar_auditoria
from app.services.saldo import ESTADOS_COMPROBANTE_ACTIVO, saldo_de
from app.workers.celery_app import TAREA_PROCESAR_COMPROBANTE, celery_app
from app.workers.encolar import encolar_tras_commit

# Estados de la deuda sobre los que cualquiera del equipo adjunta: hay un intento de pago.
ESTADOS_CON_INTENTO = ("en_proceso", "por_validar")
# Estados sobre los que solo el gerente adjunta: paga él sin iniciar antes el intento (CA09).
ESTADOS_SIN_INTENTO = ("pendiente", "pagada_parcial")

MENSAJE_DUPLICADO_AJENO = "Este archivo no se puede usar como comprobante."


@dataclass(frozen=True)
class Reparto:
    deuda: Deuda
    monto_aplicado: Decimal


def no_encontrado() -> ErrorApi:
    return ErrorApi(404, "NO_ENCONTRADO", "No se encontró una de las deudas.", "deudas")


def bloquear_deudas(db: Session, ids: list[uuid.UUID], gerente_id: uuid.UUID) -> list[Deuda]:
    """Deudas del gerente bloqueadas en orden de id, el mismo en toda transacción, para que dos
    subidas sobre deudas comunes no se interbloqueen. Una ajena responde igual que una que no
    existe."""
    deudas = list(
        db.scalars(
            select(Deuda)
            .where(Deuda.id.in_(ids), Deuda.gerente_id == gerente_id)
            .order_by(Deuda.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    )
    if len(deudas) != len(ids):
        raise no_encontrado()
    return deudas


def aplicado_en_curso(db: Session, deuda_id: uuid.UUID) -> Decimal:
    """Lo que reservan sobre la deuda los comprobantes que todavía pueden validarse."""
    total = db.scalar(
        select(func.coalesce(func.sum(ComprobanteDeuda.monto_aplicado), Decimal("0.00")))
        .join(Comprobante, Comprobante.id == ComprobanteDeuda.comprobante_id)
        .where(
            ComprobanteDeuda.deuda_id == deuda_id,
            Comprobante.estado.in_(ESTADOS_COMPROBANTE_ACTIVO),
        )
    )
    return total or Decimal("0.00")


def solo_asistente(usuario: Usuario) -> None:
    """El voucher lo sube la asistente que pagó; el gerente lo valida (TASK-109)."""
    if usuario.rol != "asistente":
        raise ErrorApi(403, "SIN_PERMISO", "No tienes permiso para realizar esta acción.")


def comprobar_estado(deuda: Deuda) -> None:
    if deuda.estado in ESTADOS_CON_INTENTO:
        return
    if deuda.estado in ESTADOS_SIN_INTENTO:
        raise ErrorApi(
            409,
            "SIN_INTENTO",
            "Inicia el pago de la deuda antes de adjuntar su comprobante.",
            "deudas",
        )
    raise ErrorApi(
        409,
        "ESTADO_NO_PERMITIDO",
        "El estado de una de las deudas no permite adjuntar comprobantes.",
        "deudas",
    )


def preparar_repartos(
    db: Session,
    gerente_id: uuid.UUID,
    entradas: list[RepartoComprobanteEntrada],
) -> list[Reparto]:
    if not entradas:
        raise ErrorApi(422, "VALIDACION", "Indica al menos una deuda.", "deudas")
    ids = [e.deuda_id for e in entradas]
    if len(set(ids)) != len(ids):
        raise ErrorApi(422, "VALIDACION", "Una deuda solo puede aparecer una vez.", "deudas")
    deudas = {d.id: d for d in bloquear_deudas(db, ids, gerente_id)}
    if len({d.moneda for d in deudas.values()}) > 1:
        raise ErrorApi(
            422,
            "MONEDA_DISTINTA",
            "Un comprobante solo puede cubrir deudas de la misma moneda.",
            "deudas",
        )
    repartos = []
    for entrada in entradas:
        deuda = deudas[entrada.deuda_id]
        comprobar_estado(deuda)
        saldo = saldo_de(db, deuda)
        disponible = (saldo or Decimal(0)) - aplicado_en_curso(db, deuda.id)
        if disponible <= 0:
            raise ErrorApi(
                409,
                "SIN_SALDO",
                "Una de las deudas no tiene saldo por cubrir con un comprobante nuevo.",
                "deudas",
            )
        monto = entrada.monto_aplicado if entrada.monto_aplicado is not None else disponible
        if monto > disponible:
            raise ErrorApi(
                422,
                "VALIDACION",
                f"El monto aplicado supera el saldo por cubrir ({deuda.moneda} {disponible}).",
                "deudas",
                datos={"deuda_id": str(deuda.id), "disponible": str(disponible)},
            )
        repartos.append(Reparto(deuda, monto))
    return repartos


def duplicado(db: Session, hash_sha256: str, gerente_id: uuid.UUID) -> ErrorApi | None:
    """Error para un archivo ya registrado en un comprobante no rechazado, o None si es nuevo."""
    existente = db.scalar(
        select(Comprobante).where(
            Comprobante.hash_sha256 == hash_sha256, Comprobante.estado != "rechazado"
        )
    )
    if existente is None:
        return None
    if existente.gerente_id != gerente_id:
        return ErrorApi(409, "DUPLICADO", MENSAJE_DUPLICADO_AJENO, "archivo")
    deudas = db.scalars(
        select(ComprobanteDeuda.deuda_id)
        .where(ComprobanteDeuda.comprobante_id == existente.id)
        .order_by(ComprobanteDeuda.deuda_id)
    )
    return ErrorApi(
        409,
        "DUPLICADO",
        "Este comprobante ya fue registrado.",
        "archivo",
        datos={"comprobante_id": str(existente.id), "deudas": [str(d) for d in deudas]},
    )


def registrar(
    db: Session,
    usuario: Usuario,
    gerente_id: uuid.UUID,
    archivo: ArchivoValidado,
    repartos: list[Reparto],
    ahora: datetime,
    reemplaza_a_id: uuid.UUID | None = None,
) -> Comprobante:
    error = duplicado(db, archivo.hash_sha256, gerente_id)
    if error is not None:
        raise error
    comprobante_id = uuid.uuid4()
    ruta = ruta_comprobante(gerente_id, comprobante_id, archivo.extension)
    guardar_privado(ruta, archivo)
    try:
        comprobante = Comprobante(
            id=comprobante_id,
            gerente_id=gerente_id,
            archivo_url=ruta,
            archivo_tipo=archivo.extension,
            archivo_bytes=len(archivo.contenido),
            hash_sha256=archivo.hash_sha256,
            moneda=repartos[0].deuda.moneda,
            estado="procesando",
            reemplaza_a_id=reemplaza_a_id,
            subido_por=usuario.id,
            # Hora de la aplicación, no now() de la base: la bandeja compara esta fecha con
            # pago_iniciado_en, que también la pone la aplicación (TASK-49).
            creado_en=ahora,
        )
        with db.begin_nested():
            db.add(comprobante)
            db.flush()
            for reparto in repartos:
                db.add(
                    ComprobanteDeuda(
                        comprobante_id=comprobante.id,
                        deuda_id=reparto.deuda.id,
                        monto_aplicado=reparto.monto_aplicado,
                    )
                )
            db.flush()
    except IntegrityError as error_bd:
        eliminar_privado(ruta)
        if "uq_comprobante_hash" not in str(error_bd.orig):
            raise
        # Otra subida del mismo archivo se confirmó entre la consulta y la inserción.
        raise duplicado(db, archivo.hash_sha256, gerente_id) or ErrorApi(
            409, "DUPLICADO", MENSAJE_DUPLICADO_AJENO, "archivo"
        ) from error_bd
    except BaseException:
        eliminar_privado(ruta)
        raise
    for reparto in repartos:
        reparto.deuda.estado = "por_validar"
    encolar_tras_commit(
        db, celery_app.signature(TAREA_PROCESAR_COMPROBANTE, args=(str(comprobante.id),))
    )
    return comprobante


def subir_comprobante(
    db: Session,
    usuario: Usuario,
    gerente_id: uuid.UUID,
    archivo: ArchivoValidado,
    entradas: list[RepartoComprobanteEntrada],
    *,
    origen: Origen,
    ahora: datetime | None = None,
) -> Comprobante:
    solo_asistente(usuario)
    repartos = preparar_repartos(db, gerente_id, entradas)
    comprobante = registrar(db, usuario, gerente_id, archivo, repartos, ahora or ahora_lima())
    registrar_auditoria(
        db,
        usuario,
        Accion.COMPROBANTE_SUBIDO,
        "comprobante",
        comprobante.id,
        {
            "deudas": [
                {"deuda_id": r.deuda.id, "monto_aplicado": r.monto_aplicado} for r in repartos
            ],
            "moneda": comprobante.moneda,
            "archivo_tipo": comprobante.archivo_tipo,
        },
        origen=origen,
    )
    return comprobante


def comprobante_visible(
    db: Session, comprobante_id: uuid.UUID, gerente_id: uuid.UUID, *, bloquear: bool = False
) -> Comprobante:
    """Comprobante del gerente; si no existe o es ajeno, el mismo 404."""
    consulta = select(Comprobante).where(
        Comprobante.id == comprobante_id, Comprobante.gerente_id == gerente_id
    )
    if bloquear:
        consulta = consulta.with_for_update().execution_options(populate_existing=True)
    comprobante = db.scalar(consulta)
    if comprobante is None:
        raise ErrorApi(404, "NO_ENCONTRADO", "No se encontró el comprobante.")
    return comprobante


def reemplazo_de(db: Session, comprobante_id: uuid.UUID) -> Comprobante | None:
    return db.scalar(select(Comprobante).where(Comprobante.reemplaza_a_id == comprobante_id))


def repartos_de(db: Session, comprobante_id: uuid.UUID) -> list[ComprobanteDeuda]:
    return list(
        db.scalars(
            select(ComprobanteDeuda)
            .where(ComprobanteDeuda.comprobante_id == comprobante_id)
            .order_by(ComprobanteDeuda.deuda_id)
        )
    )


def reemplazar_comprobante(
    db: Session,
    usuario: Usuario,
    gerente_id: uuid.UUID,
    comprobante_id: uuid.UUID,
    archivo: ArchivoValidado,
    *,
    origen: Origen,
    ahora: datetime | None = None,
) -> Comprobante:
    """Sube una versión nueva de un comprobante rechazado con su mismo reparto (CA08)."""
    solo_asistente(usuario)
    # El anterior se bloquea antes que las deudas: dos reemplazos simultáneos se turnan y el
    # segundo ve la versión que creó el primero.
    anterior = comprobante_visible(db, comprobante_id, gerente_id, bloquear=True)
    if anterior.estado != "rechazado":
        raise ErrorApi(
            409, "ESTADO_NO_PERMITIDO", "Solo se puede reemplazar un comprobante rechazado."
        )
    if reemplazo_de(db, anterior.id) is not None:
        raise ErrorApi(409, "YA_REEMPLAZADO", "Este comprobante ya fue reemplazado.")
    entradas = [
        RepartoComprobanteEntrada(deuda_id=r.deuda_id, monto_aplicado=r.monto_aplicado)
        for r in repartos_de(db, anterior.id)
    ]
    repartos = preparar_repartos(db, gerente_id, entradas)
    comprobante = registrar(
        db, usuario, gerente_id, archivo, repartos, ahora or ahora_lima(), anterior.id
    )
    registrar_auditoria(
        db,
        usuario,
        Accion.COMPROBANTE_REEMPLAZADO,
        "comprobante",
        comprobante.id,
        {"reemplaza_a_id": anterior.id, "archivo_tipo": comprobante.archivo_tipo},
        origen=origen,
    )
    return comprobante
