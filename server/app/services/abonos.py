"""Abonos de un comprobante validado (H24 CA05; TASK-87, reutilizado por la revisión de TASK-88).

aplicar_abonos recibe el comprobante y sus deudas ya bloqueados (comprobante y luego deudas en
orden de id) y el abono decidido para cada deuda:

1. Vuelve a calcular el saldo de cada deuda con lo validado hasta ahora. Si un abono supera el
   saldo (otro comprobante de la misma deuda se validó antes), no aplica nada y devuelve esa
   deuda: dos comprobantes no cobran el mismo saldo (contrato H24, punto 3).
2. Ajusta monto_aplicado del reparto al abono (en un pago parcial, el monto del comprobante) y
   marca el comprobante como validado. Solo los validados restan del saldo (app/services/saldo.py).
3. Cada deuda queda pagada con saldo cero o pagada_parcial con saldo positivo, y su intento de
   pago se cierra. Si otro comprobante activo la sigue cubriendo, queda en por_validar hasta que
   ese se resuelva.
4. Avisa al gerente de cada deuda pagada, una sola vez por deuda (clave_evento).

No hace commit. Llamarlo dos veces sobre el mismo comprobante no es posible: quien llama solo lo
hace con un comprobante que todavía no está validado y lo tiene bloqueado.
"""

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models import Comprobante, ComprobanteDeuda, Deuda, Usuario
from app.services.notificaciones import TipoNotificacion, notificar
from app.services.saldo import ESTADOS_COMPROBANTE_ACTIVO, aplicado_de


def otro_activo(db: Session, deuda_id: uuid.UUID, comprobante_id: uuid.UUID) -> bool:
    """Si otro comprobante que todavía puede validarse cubre la deuda."""
    return (
        db.scalar(
            select(Comprobante.id)
            .join(ComprobanteDeuda, ComprobanteDeuda.comprobante_id == Comprobante.id)
            .where(
                ComprobanteDeuda.deuda_id == deuda_id,
                Comprobante.id != comprobante_id,
                Comprobante.estado.in_(ESTADOS_COMPROBANTE_ACTIVO),
            )
            .limit(1)
        )
        is not None
    )


def aplicar_abonos(
    db: Session,
    comprobante: Comprobante,
    deudas: list[Deuda],
    aplicados: dict[uuid.UUID, Decimal],
    ahora: datetime,
) -> Deuda | None:
    """Aplica los abonos y devuelve None, o devuelve la primera deuda cuyo saldo no alcanza sin
    haber cambiado nada."""
    saldos = {}
    for deuda in deudas:
        assert deuda.monto is not None, f"La deuda {deuda.id} por validar no tiene monto"
        saldo = deuda.monto - aplicado_de(db, deuda.id)
        if aplicados[deuda.id] > saldo:
            return deuda
        saldos[deuda.id] = saldo - aplicados[deuda.id]

    for deuda in deudas:
        db.execute(
            update(ComprobanteDeuda)
            .where(
                ComprobanteDeuda.comprobante_id == comprobante.id,
                ComprobanteDeuda.deuda_id == deuda.id,
            )
            .values(monto_aplicado=aplicados[deuda.id])
        )
    comprobante.estado = "validado"
    db.flush()

    gerente = db.get(Usuario, comprobante.gerente_id)
    for deuda in deudas:
        if saldos[deuda.id] > 0 and otro_activo(db, deuda.id, comprobante.id):
            continue
        deuda.estado = "pagada" if saldos[deuda.id] == 0 else "pagada_parcial"
        deuda.pago_iniciado_por = None
        deuda.pago_iniciado_en = None
        deuda.pago_realizado = False
        deuda.pago_realizado_en = None
        deuda.recordatorios_enviados = 0
        if deuda.estado == "pagada" and gerente is not None:
            notificar(
                db,
                gerente,
                TipoNotificacion.DEUDA_PAGADA,
                "Deuda pagada",
                f"Se validó el comprobante y la deuda quedó pagada ({deuda.moneda} {deuda.monto}).",
                deuda_id=deuda.id,
                clave_evento=f"deuda_pagada:{deuda.id}",
                ahora=ahora,
            )
    return None
