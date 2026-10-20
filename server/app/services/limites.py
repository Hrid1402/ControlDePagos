"""Servicio de consulta y validación de límites y solicitudes (H05, TASK-22).

Reutiliza los modelos Limite y SolicitudAprobacion existentes sobre el esquema.
"""

import uuid
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errores import ErrorApi
from app.models import Deuda, Limite, SolicitudAprobacion


def obtener_limite(db: Session, gerente_id: uuid.UUID) -> Limite | None:
    """Devuelve la configuración de límites del gerente si existe."""
    return db.get(Limite, gerente_id)


def fijar_limite(
    db: Session,
    gerente_id: uuid.UUID,
    por_pago: Decimal | None,
    mensual: Decimal | None,
) -> Limite:
    """Crea o actualiza los límites opcionales del gerente validando las reglas de negocio."""
    if por_pago is not None and por_pago <= Decimal("0"):
        raise ErrorApi(
            400, "MONTO_INVALIDO", "El límite por pago debe ser mayor que cero.", "por_pago"
        )
    if mensual is not None and mensual <= Decimal("0"):
        raise ErrorApi(
            400, "MONTO_INVALIDO", "El límite mensual debe ser mayor que cero.", "mensual"
        )
    if por_pago is not None and mensual is not None and por_pago > mensual:
        raise ErrorApi(
            400,
            "LIMITE_INVALIDO",
            "El límite por pago no puede ser mayor que el mensual.",
            "por_pago",
        )

    limite = db.get(Limite, gerente_id)
    if limite is None:
        limite = Limite(gerente_id=gerente_id, por_pago=por_pago, mensual=mensual)
        db.add(limite)
    else:
        limite.por_pago = por_pago
        limite.mensual = mensual

    db.flush()
    return limite


def solicitudes_de_gerente(
    db: Session,
    gerente_id: uuid.UUID,
    estado: str | None = None,
) -> list[SolicitudAprobacion]:
    """Obtiene las solicitudes vinculadas al equipo del gerente garantizando aislamiento tenant."""
    consulta = (
        select(SolicitudAprobacion)
        .join(Deuda, SolicitudAprobacion.deuda_id == Deuda.id)
        .where(Deuda.gerente_id == gerente_id)
    )
    if estado is not None:
        consulta = consulta.where(SolicitudAprobacion.estado == estado)

    consulta = consulta.order_by(SolicitudAprobacion.creado_en.desc())
    return list(db.scalars(consulta).all())
