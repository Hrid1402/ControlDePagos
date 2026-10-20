from typing import Annotated

from fastapi import APIRouter, File, Form, UploadFile, status

from app.core.dependencias import GerenteId, SesionDb, UsuarioActual
from app.schemas.comprobantes import ComprobanteSalida, RepartoComprobanteEntrada
from app.services.archivos import validar_archivo
from app.services.comprobantes import subir_comprobante

router = APIRouter(prefix="/comprobantes", tags=["comprobantes"])


@router.post("", response_model=ComprobanteSalida, status_code=status.HTTP_201_CREATED)
async def subir(
    archivo: Annotated[UploadFile, File()],
    deudas: Annotated[str, Form()],
    db: SesionDb,
    usuario: UsuarioActual,
    gerente_id: GerenteId,
) -> ComprobanteSalida:
    import json

    repartos = [RepartoComprobanteEntrada.model_validate(dato) for dato in json.loads(deudas)]
    validado = await validar_archivo(archivo)
    comprobante = subir_comprobante(db, usuario, gerente_id, validado, repartos)
    db.commit()
    return ComprobanteSalida.model_validate(comprobante, from_attributes=True)
