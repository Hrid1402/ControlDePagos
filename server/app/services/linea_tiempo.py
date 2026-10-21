"""Línea de tiempo de una deuda (H17 CA04, TASK-53): qué pasó, quién lo hizo y cuándo.

Reúne solo eventos de esta deuda: su auditoría, la de sus comprobantes y la de sus órdenes, más
los resultados automáticos de la validación y la creación por recurrencia, que no tienen autor.
No expone la auditoría del gerente ni el detalle completo de cada evento, solo las claves de
LECTURA. El texto de cada tipo lo pone el cliente.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session, aliased

from app.models import Auditoria, Comprobante, Deuda, OrdenPago, Usuario

# Claves del detalle de auditoría que la línea de tiempo deja leer.
LECTURA = frozenset(
    {
        "monto",
        "moneda",
        "estado_anterior",
        "estado_nuevo",
        "motivo",
        "motivo_codigo",
        "autorizacion",
        "fijada",
        "oculta_hasta",
        "monto_anterior",
        "monto_nuevo",
    }
)


@dataclass(frozen=True)
class Evento:
    tipo: str
    fecha: datetime
    actor: tuple[str, str | None] | None
    detalle: dict[str, Any]


def linea_de_tiempo(db: Session, deuda: Deuda, comprobantes: list[Comprobante]) -> list[Evento]:
    ids_comprobantes = [c.id for c in comprobantes]
    ids_ordenes = select(OrdenPago.id).where(OrdenPago.deuda_id == deuda.id)
    autor = aliased(Usuario)
    filas = db.execute(
        select(Auditoria, autor.rol)
        .outerjoin(autor, autor.id == Auditoria.usuario_id)
        .where(
            or_(
                and_(Auditoria.entidad == "deuda", Auditoria.entidad_id == deuda.id),
                and_(
                    Auditoria.entidad == "comprobante",
                    Auditoria.entidad_id.in_(ids_comprobantes),
                ),
                and_(Auditoria.entidad == "orden_pago", Auditoria.entidad_id.in_(ids_ordenes)),
            ),
            Auditoria.gerente_id == deuda.gerente_id,
        )
    )
    eventos = [
        Evento(
            tipo=registro.accion,
            fecha=registro.creado_en,
            actor=(registro.usuario_nombre, rol),
            detalle={k: v for k, v in registro.detalle.items() if k in LECTURA},
        )
        for registro, rol in filas
    ]
    if not any(e.tipo == "deuda_creada" for e in eventos):
        # Las deudas que crea una recurrencia no tienen autor: se registran como del sistema.
        eventos.append(Evento("deuda_creada", deuda.creado_en, None, {"origen": deuda.origen}))
    for c in comprobantes:
        if c.estado in ("validado", "rechazado", "en_revision") and c.revisado_por is None:
            eventos.append(
                Evento(
                    f"comprobante_{c.estado}",
                    c.actualizado_en,
                    None,
                    {"comprobante_id": str(c.id), "motivo_codigo": c.motivo_codigo},
                )
            )
    return sorted(eventos, key=lambda e: e.fecha, reverse=True)
