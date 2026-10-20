import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

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


def subir_comprobante(
    db: Session,
    usuario: Usuario,
    gerente_id: uuid.UUID,
    archivo: ArchivoValidado,
    repartos: list[RepartoComprobanteEntrada],
    ahora: datetime | None = None,
) -> Comprobante:
    if not repartos:
        raise ErrorApi(422, "VALIDACION", "Indica al menos una deuda.", "deudas")
    ids = [r.deuda_id for r in repartos]
    if len(set(ids)) != len(ids):
        raise ErrorApi(422, "VALIDACION", "Una deuda solo puede aparecer una vez.", "deudas")
    deudas = list(db.scalars(select(Deuda).where(Deuda.id.in_(ids)).with_for_update()))
    if len(deudas) != len(ids) or any(d.gerente_id != gerente_id for d in deudas):
        raise ErrorApi(404, "NO_ENCONTRADO", "No se encontró una de las deudas.", "deudas")
    existente = db.scalar(select(Comprobante).where(Comprobante.hash_sha256 == archivo.hash_sha256))
    if existente is not None:
        raise ErrorApi(409, "DUPLICADO", "Este comprobante ya fue registrado.", "archivo")
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
            estado="procesando",
            subido_por=usuario.id,
            creado_en=ahora or ahora_lima(),
        )
        db.add(comprobante)
        db.flush()
        for reparto in repartos:
            db.add(
                ComprobanteDeuda(
                    comprobante_id=comprobante.id,
                    deuda_id=reparto.deuda_id,
                    monto_aplicado=reparto.monto_aplicado,
                )
            )
        for deuda in deudas:
            deuda.estado = "por_validar"
        db.flush()
    except BaseException:
        eliminar_privado(ruta)
        raise
    return comprobante
