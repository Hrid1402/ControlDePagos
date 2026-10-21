"""Revisión de comprobantes por el gerente (H24 CA07, TASK-88).

El gerente aprueba o rechaza con un clic un comprobante en revisión. Todo en una transacción con
el comprobante y sus deudas bloqueados (el mismo orden que el worker de OCR):

- Aprobar aplica los abonos con el servicio común (app/services/abonos.py), que vuelve a
  comprobar el saldo. Sin reparto, aplica el reparto confirmado al subir. Con reparto, el gerente
  lo corrige para las mismas deudas: así se resuelve un monto mayor o un monto menor entre varias
  deudas. Ningún abono supera el saldo de su deuda y, si se leyó el monto del comprobante, la
  suma no lo supera (contrato H24, punto 2).
- Rechazar exige el motivo, que recibe quien subió el comprobante, y devuelve sus deudas al
  intento vigente para adjuntar otro o reemplazarlo.

Idempotente: repetir la misma decisión (doble clic) devuelve el comprobante sin efectos nuevos;
la decisión contraria, o decidir sobre uno que no está en revisión, responde 409. Auditoría,
notificaciones y el evento comprobante_resultado salen solo si la transacción se confirma.
"""

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy.orm import Session

from app.core.dependencias import Origen
from app.core.errores import ErrorApi
from app.core.tiempo import ahora_lima
from app.models import Comprobante, Usuario
from app.schemas.comprobantes import RepartoComprobanteEntrada
from app.services.abonos import aplicar_abonos
from app.services.auditoria import Accion, registrar_auditoria
from app.services.comprobantes import comprobante_visible, repartos_de
from app.services.validacion import avisar, deudas_de, resolver

DECIDIBLES = ("en_revision", "por_confirmar")
MENSAJE_APROBADO = "El gerente aprobó el comprobante."


def no_decidible(comprobante: Comprobante) -> ErrorApi:
    if comprobante.estado == "procesando":
        return ErrorApi(
            409,
            "ESTADO_NO_PERMITIDO",
            "El comprobante todavía se está validando. Espera el resultado.",
        )
    return ErrorApi(409, "ESTADO_NO_PERMITIDO", "El comprobante ya fue resuelto.")


def abonos_de(
    db: Session, comprobante: Comprobante, entradas: list[RepartoComprobanteEntrada] | None
) -> dict[uuid.UUID, Decimal]:
    actuales = {r.deuda_id: r.monto_aplicado for r in repartos_de(db, comprobante.id)}
    if entradas is None:
        return actuales
    if {e.deuda_id for e in entradas} != set(actuales) or len(entradas) != len(actuales):
        raise ErrorApi(
            422,
            "VALIDACION",
            "El reparto debe incluir cada deuda del comprobante una sola vez.",
            "deudas",
        )
    abonos = {e.deuda_id: e.monto_aplicado or actuales[e.deuda_id] for e in entradas}
    total = sum(abonos.values(), Decimal(0))
    if comprobante.monto is not None and total > comprobante.monto:
        raise ErrorApi(
            422,
            "VALIDACION",
            f"El reparto suma {comprobante.moneda} {total}, más que el comprobante "
            f"({comprobante.moneda} {comprobante.monto}).",
            "deudas",
        )
    return abonos


def aprobar_comprobante(
    db: Session,
    gerente: Usuario,
    comprobante_id: uuid.UUID,
    entradas: list[RepartoComprobanteEntrada] | None = None,
    *,
    origen: Origen,
    ahora: datetime | None = None,
) -> Comprobante:
    momento = ahora or ahora_lima()
    comprobante = comprobante_visible(db, comprobante_id, gerente.id, bloquear=True)
    if comprobante.estado == "validado" and comprobante.revisado_por is not None:
        return comprobante
    if comprobante.estado not in DECIDIBLES:
        raise no_decidible(comprobante)
    abonos = abonos_de(db, comprobante, entradas)
    deudas = deudas_de(db, comprobante)
    sin_saldo = aplicar_abonos(db, comprobante, deudas, abonos, momento)
    if sin_saldo is not None:
        raise ErrorApi(
            409,
            "SIN_SALDO",
            "El abono supera el saldo de una de las deudas. Corrige el reparto.",
            "deudas",
            datos={"deuda_id": str(sin_saldo.id)},
        )
    comprobante.revisado_por = gerente.id
    comprobante.revisado_en = momento
    comprobante.datos_extraidos = {
        **comprobante.datos_extraidos,
        "observacion": MENSAJE_APROBADO,
    }
    registrar_auditoria(
        db,
        gerente,
        Accion.COMPROBANTE_APROBADO,
        "comprobante",
        comprobante.id,
        {
            "deudas": [{"deuda_id": k, "monto_aplicado": v} for k, v in abonos.items()],
            "motivo_codigo": comprobante.motivo_codigo,
        },
        origen=origen,
    )
    avisar(db, comprobante, deudas, momento)
    return comprobante


def rechazar_comprobante(
    db: Session,
    gerente: Usuario,
    comprobante_id: uuid.UUID,
    motivo: str,
    *,
    origen: Origen,
    ahora: datetime | None = None,
) -> Comprobante:
    momento = ahora or ahora_lima()
    comprobante = comprobante_visible(db, comprobante_id, gerente.id, bloquear=True)
    if comprobante.estado == "rechazado" and comprobante.revisado_por is not None:
        return comprobante
    if comprobante.estado not in DECIDIBLES:
        raise no_decidible(comprobante)
    motivo = " ".join(motivo.split())
    comprobante.revisado_por = gerente.id
    comprobante.revisado_en = momento
    resolver(
        db,
        comprobante,
        "rechazado",
        comprobante.motivo_codigo,
        f"El gerente rechazó el comprobante: {motivo}",
        momento,
    )
    registrar_auditoria(
        db,
        gerente,
        Accion.COMPROBANTE_RECHAZADO,
        "comprobante",
        comprobante.id,
        {"motivo": motivo, "motivo_codigo": comprobante.motivo_codigo},
        origen=origen,
    )
    return comprobante
