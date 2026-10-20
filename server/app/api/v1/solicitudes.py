"""Solicitudes de aprobación del gerente (H05, TASK-24).

CA07: aprobar o rechazar desde la app. CA08: motivo opcional y aviso a la asistente.
CA10: lista por estado. La solicitud la crea el inicio de pago cuando supera un límite.
"""

import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Query
from sqlalchemy.orm import Session

from app.core.dependencias import OrigenSolicitud, SesionDb, SoloGerente
from app.core.paginacion import Pagina, ParametrosPagina, paginar
from app.models import SolicitudAprobacion
from app.schemas.limites import (
    RechazarSolicitudEntrada,
    SolicitudAprobacionSalida,
    SolicitudListaSalida,
)
from app.services.limites import consulta_solicitudes, contexto_de, resolver_solicitud

router = APIRouter(prefix="/solicitudes", tags=["solicitudes"])

EstadoSolicitud = Literal["pendiente", "aprobada", "rechazada"]


def salida(db: Session, solicitudes: list[SolicitudAprobacion]) -> list[SolicitudListaSalida]:
    contexto = contexto_de(db, solicitudes)
    return [
        SolicitudListaSalida(
            **SolicitudAprobacionSalida.model_validate(s).model_dump(),
            servicio=contexto[s.id].servicio,
            fecha_vencimiento=contexto[s.id].fecha_vencimiento,
            asistente=contexto[s.id].asistente,
            resuelta_por_nombre=contexto[s.id].resuelta_por,
        )
        for s in solicitudes
    ]


@router.get("", response_model=Pagina[SolicitudListaSalida])
def listar(
    gerente: SoloGerente,
    db: SesionDb,
    pagina: ParametrosPagina,
    estado: Annotated[EstadoSolicitud | None, Query()] = None,
) -> Pagina[SolicitudListaSalida]:
    """Solicitudes del gerente, las más recientes primero, filtradas por estado (CA10)."""
    resultado = paginar(db, consulta_solicitudes(gerente.id, estado), pagina)
    return Pagina(items=salida(db, resultado.items), total=resultado.total, page=resultado.page)


@router.post("/{solicitud_id}/aprobar", response_model=SolicitudListaSalida)
def aprobar(
    solicitud_id: uuid.UUID, gerente: SoloGerente, db: SesionDb, origen: OrigenSolicitud
) -> SolicitudListaSalida:
    """Autoriza solo el importe y la moneda de la solicitud; la asistente inicia el pago (CA07)."""
    solicitud = resolver_solicitud(db, gerente, solicitud_id, "aprobada", origen=origen)
    db.commit()
    return salida(db, [solicitud])[0]


@router.post("/{solicitud_id}/rechazar", response_model=SolicitudListaSalida)
def rechazar(
    solicitud_id: uuid.UUID,
    gerente: SoloGerente,
    db: SesionDb,
    origen: OrigenSolicitud,
    datos: RechazarSolicitudEntrada | None = None,
) -> SolicitudListaSalida:
    """Rechaza con motivo opcional y avisa a la asistente (CA08)."""
    motivo = datos.motivo if datos else None
    solicitud = resolver_solicitud(db, gerente, solicitud_id, "rechazada", motivo, origen=origen)
    db.commit()
    return salida(db, [solicitud])[0]
