"""Empresas comunes con su patrón de código (H10 CA01 y CA02). Las consultan el gerente y su
asistente al registrar un servicio."""

from fastapi import APIRouter

from app.core.dependencias import GerenteId, SesionDb
from app.schemas.servicios import EmpresaSalida, TipoServicioEmpresa
from app.services.empresas import listar_empresas

router = APIRouter(prefix="/empresas", tags=["empresas"])


@router.get("", response_model=list[EmpresaSalida])
def listar(
    db: SesionDb, _gerente_id: GerenteId, tipo_servicio: TipoServicioEmpresa | None = None
) -> list[EmpresaSalida]:
    return [
        EmpresaSalida(
            id=empresa.id,
            nombre=empresa.nombre,
            tipo_servicio=empresa.tipo_servicio,
            patron_codigo=empresa.patron_codigo,
        )
        for empresa in listar_empresas(db, tipo_servicio)
    ]
