"""Bandeja de la asistente (H15): lista por prioridad con contadores, fijar y recordar mañana.

La bandeja la ven el gerente y su asistente; fijar y recordar mañana son solo de la asistente.
Errores: 404 NO_ENCONTRADO (deuda o categoría inexistente o de otro gerente), 403 SIN_PERMISO,
422 VALIDACION y 409 ESTADO_NO_PERMITIDO u ORDEN_URGENTE_ACTIVA.
"""

import uuid

from fastapi import APIRouter

from app.core.dependencias import GerenteId, OrigenSolicitud, SesionDb, SoloAsistente
from app.core.paginacion import ParametrosPagina
from app.models import Deuda
from app.schemas.bandeja import (
    BandejaSalida,
    CategoriaBandeja,
    ContadoresBandeja,
    DeudaPrioridadSalida,
    EnProcesoBandeja,
    FijarEntrada,
    ItemBandeja,
    OrdenUrgenteBandeja,
)
from app.services.auditoria import nombre_de
from app.services.bandeja import (
    FilaBandeja,
    Pestana,
    consultar_bandeja,
    fijar,
    recordar_manana,
)

router = APIRouter(tags=["bandeja"])


def item_salida(fila: FilaBandeja) -> ItemBandeja:
    deuda, orden, iniciador = fila.deuda, fila.orden, fila.iniciador
    en_proceso = None
    if deuda.estado == "en_proceso" and iniciador is not None:
        en_proceso = EnProcesoBandeja(
            usuario_id=iniciador.id,
            rol=iniciador.rol,
            nombre=nombre_de(iniciador),
            desde=deuda.pago_iniciado_en,
        )
    return ItemBandeja(
        id=deuda.id,
        empresa=fila.empresa,
        alias=fila.servicio.alias,
        codigo_suministro=fila.servicio.codigo_suministro,
        lugar_pago=fila.servicio.lugar_pago,
        categoria=CategoriaBandeja.model_validate(fila.categoria, from_attributes=True),
        monto=deuda.monto,
        moneda=deuda.moneda,
        saldo=fila.saldo,
        estado=deuda.estado,
        fecha_vencimiento=deuda.fecha_vencimiento,
        dias_restantes=fila.dias_restantes,
        nivel=fila.nivel,
        etiqueta=fila.etiqueta,
        fijada=deuda.fijada,
        orden_urgente=(
            OrdenUrgenteBandeja(id=orden.id, estado=orden.estado, plazo=orden.plazo)
            if orden is not None
            else None
        ),
        en_proceso=en_proceso,
        comprobante_estado=fila.comprobante_estado,
    )


def prioridad_salida(deuda: Deuda) -> DeudaPrioridadSalida:
    return DeudaPrioridadSalida(id=deuda.id, fijada=deuda.fijada, oculta_hasta=deuda.oculta_hasta)


@router.get("/bandeja")
def ver_bandeja(
    db: SesionDb,
    gerente_id: GerenteId,
    parametros: ParametrosPagina,
    pestana: Pestana = Pestana.POR_PAGAR,
    categoria: uuid.UUID | None = None,
) -> BandejaSalida:
    """Deudas de la pestaña por prioridad y los contadores de las tres pestañas."""
    bandeja = consultar_bandeja(db, gerente_id, pestana, parametros, categoria)
    return BandejaSalida(
        items=[item_salida(fila) for fila in bandeja.filas],
        total=bandeja.total,
        page=parametros.page,
        contadores=ContadoresBandeja(**{p.value: n for p, n in bandeja.contadores.items()}),
    )


@router.post("/deudas/{deuda_id}/fijar")
def fijar_deuda(
    deuda_id: uuid.UUID,
    datos: FijarEntrada,
    db: SesionDb,
    usuario: SoloAsistente,
    origen: OrigenSolicitud,
) -> DeudaPrioridadSalida:
    deuda = fijar(db, usuario, deuda_id, datos.fijada, origen=origen)
    db.commit()
    return prioridad_salida(deuda)


@router.post("/deudas/{deuda_id}/recordar-manana")
def recordar_deuda_manana(
    deuda_id: uuid.UUID, db: SesionDb, usuario: SoloAsistente, origen: OrigenSolicitud
) -> DeudaPrioridadSalida:
    """Oculta la deuda hasta las 08:00 del día siguiente en Lima."""
    deuda = recordar_manana(db, usuario, deuda_id, origen=origen)
    db.commit()
    return prioridad_salida(deuda)
