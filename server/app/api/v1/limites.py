"""Límites de gasto del gerente y consumo del mes (H05, TASK-23).

CA01 a CA04, CA11 y CA12. El control al iniciar un pago vive en app/services/pagos.py (TASK-75):
compara cada pago de la asistente con estos límites y, si los supera, crea la solicitud.
"""

from fastapi import APIRouter

from app.core.dependencias import OrigenSolicitud, SesionDb, SoloGerente
from app.schemas.limites import ConfigurarLimiteEntrada, LimitesConsumoSalida
from app.services.limites import actualizar_limites, limites_con_consumo

router = APIRouter(prefix="/limites", tags=["limites"])


@router.get("", response_model=LimitesConsumoSalida)
def consultar(gerente: SoloGerente, db: SesionDb) -> LimitesConsumoSalida:
    """Límites vigentes y consumo PEN del mes en Lima (CA04)."""
    return limites_con_consumo(db, gerente)


@router.put("", response_model=LimitesConsumoSalida)
def definir(
    datos: ConfigurarLimiteEntrada, gerente: SoloGerente, db: SesionDb, origen: OrigenSolicitud
) -> LimitesConsumoSalida:
    """Reemplaza los dos límites; null es sin límite (CA02 y CA03)."""
    actualizar_limites(db, gerente, datos.por_pago, datos.mensual, origen)
    db.commit()
    return limites_con_consumo(db, gerente)
