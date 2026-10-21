"""Comprobantes de pago (H24): subida, consulta y reemplazo del archivo.

La asistente y el gerente adjuntan comprobantes de las deudas del gerente (CA09). El archivo va
en multipart: archivo y deudas, una lista JSON de {deuda_id, monto_aplicado}. Solo el gerente
aprueba o rechaza un comprobante en revisión (CA07); la asistente recibe 403 SIN_PERMISO.

Errores: 404 NO_ENCONTRADO (comprobante o deuda inexistente o de otro gerente), 422 VALIDACION o
MONEDA_DISTINTA, 409 DUPLICADO, SIN_INTENTO, ESTADO_NO_PERMITIDO, SIN_SALDO o YA_REEMPLAZADO y
503 ARCHIVO_NO_DISPONIBLE si el almacenamiento no responde.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, File, Form, UploadFile, status
from pydantic import TypeAdapter, ValidationError

from app.core.dependencias import (
    GerenteId,
    OrigenSolicitud,
    SesionDb,
    SoloGerente,
    UsuarioActual,
)
from app.core.errores import ErrorApi
from app.models import Comprobante
from app.schemas.comprobantes import (
    AprobarEntrada,
    ComprobanteSalida,
    RechazarEntrada,
    RepartoComprobanteEntrada,
    RepartoSalida,
)
from app.services.archivos import confirmar_con_archivo, enlace_firmado, validar_archivo
from app.services.comprobantes import (
    comprobante_visible,
    reemplazar_comprobante,
    reemplazo_de,
    repartos_de,
    subir_comprobante,
)
from app.services.revision_comprobantes import aprobar_comprobante, rechazar_comprobante

router = APIRouter(prefix="/comprobantes", tags=["comprobantes"])

LISTA_REPARTOS = TypeAdapter(list[RepartoComprobanteEntrada])


def leer_repartos(deudas: str) -> list[RepartoComprobanteEntrada]:
    try:
        return LISTA_REPARTOS.validate_json(deudas)
    except ValidationError:
        raise ErrorApi(
            422,
            "VALIDACION",
            "Indica las deudas como una lista de deuda_id y monto_aplicado.",
            "deudas",
        ) from None


def comprobante_salida(
    db: SesionDb, comprobante: Comprobante, *, con_enlace: bool = True
) -> ComprobanteSalida:
    reemplazo = reemplazo_de(db, comprobante.id)
    return ComprobanteSalida(
        id=comprobante.id,
        estado=comprobante.estado,
        motivo_codigo=comprobante.motivo_codigo,
        observacion=comprobante.datos_extraidos.get("observacion"),
        archivo_tipo=comprobante.archivo_tipo,
        archivo_enlace=enlace_firmado(comprobante.archivo_url) if con_enlace else None,
        moneda=comprobante.moneda,
        monto=comprobante.monto,
        entidad=comprobante.entidad,
        numero_operacion=comprobante.numero_operacion,
        fecha_pago=comprobante.fecha_pago,
        datos_extraidos=comprobante.datos_extraidos,
        deuda_sugerida_id=comprobante.deuda_sugerida_id,
        reemplaza_a_id=comprobante.reemplaza_a_id,
        reemplazado_por_id=reemplazo.id if reemplazo else None,
        subido_por=comprobante.subido_por,
        creado_en=comprobante.creado_en,
        revisado_en=comprobante.revisado_en,
        deudas=[
            RepartoSalida(deuda_id=r.deuda_id, monto_aplicado=r.monto_aplicado)
            for r in repartos_de(db, comprobante.id)
        ],
    )


@router.post("", status_code=status.HTTP_201_CREATED)
def subir(
    archivo: Annotated[UploadFile, File()],
    deudas: Annotated[str, Form()],
    db: SesionDb,
    usuario: UsuarioActual,
    gerente_id: GerenteId,
    origen: OrigenSolicitud,
) -> ComprobanteSalida:
    repartos = leer_repartos(deudas)
    validado = validar_archivo(archivo)
    comprobante = subir_comprobante(db, usuario, gerente_id, validado, repartos, origen=origen)
    confirmar_con_archivo(db, comprobante.archivo_url)
    return comprobante_salida(db, comprobante, con_enlace=False)


@router.get("/{comprobante_id}")
def ver(comprobante_id: uuid.UUID, db: SesionDb, gerente_id: GerenteId) -> ComprobanteSalida:
    return comprobante_salida(db, comprobante_visible(db, comprobante_id, gerente_id))


@router.put("/{comprobante_id}/archivo", status_code=status.HTTP_201_CREATED)
def reemplazar(
    comprobante_id: uuid.UUID,
    archivo: Annotated[UploadFile, File()],
    db: SesionDb,
    usuario: UsuarioActual,
    gerente_id: GerenteId,
    origen: OrigenSolicitud,
) -> ComprobanteSalida:
    validado = validar_archivo(archivo)
    comprobante = reemplazar_comprobante(
        db, usuario, gerente_id, comprobante_id, validado, origen=origen
    )
    confirmar_con_archivo(db, comprobante.archivo_url)
    return comprobante_salida(db, comprobante, con_enlace=False)


@router.post("/{comprobante_id}/aprobar")
def aprobar(
    comprobante_id: uuid.UUID,
    db: SesionDb,
    gerente: SoloGerente,
    origen: OrigenSolicitud,
    entrada: AprobarEntrada | None = None,
) -> ComprobanteSalida:
    deudas = entrada.deudas if entrada is not None else None
    comprobante = aprobar_comprobante(db, gerente, comprobante_id, deudas, origen=origen)
    db.commit()
    return comprobante_salida(db, comprobante)


@router.post("/{comprobante_id}/rechazar")
def rechazar(
    comprobante_id: uuid.UUID,
    entrada: RechazarEntrada,
    db: SesionDb,
    gerente: SoloGerente,
    origen: OrigenSolicitud,
) -> ComprobanteSalida:
    comprobante = rechazar_comprobante(db, gerente, comprobante_id, entrada.motivo, origen=origen)
    db.commit()
    return comprobante_salida(db, comprobante)
