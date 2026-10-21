"""Ruta de pagos presenciales (H23): deudas agrupadas por lugar de pago e inicio en lote.

La ven el gerente y su asistente; cada una ve las deudas que puede pagar ella misma. Iniciar el
lote aplica a cada deuda las reglas de iniciar-pago (límites, aprobación, intento de otra
persona) y responde 200 con el resultado de cada una. Errores del lote completo: 401, 403
SIN_PERMISO y 422 VALIDACION (lista vacía, más de 50 deudas o una repetida).
"""

import uuid

from fastapi import APIRouter

from app.core.dependencias import OrigenSolicitud, SesionDb, UsuarioActual
from app.schemas.bandeja import CategoriaBandeja
from app.schemas.ruta import (
    GrupoRutaSalida,
    IniciarRutaEntrada,
    IniciarRutaSalida,
    ItemRuta,
    ResultadoDeudaSalida,
    RutaSalida,
    TotalesRuta,
)
from app.services.ruta import (
    ESTADOS_EN_RUTA,
    FilaRuta,
    consultar_ruta,
    iniciar_ruta,
    total_iniciado,
    totales_de,
)

router = APIRouter(prefix="/ruta", tags=["ruta"])


def item_salida(fila: FilaRuta, usuario_id: uuid.UUID) -> ItemRuta:
    deuda = fila.deuda
    assert deuda.monto is not None
    return ItemRuta(
        id=deuda.id,
        empresa=fila.empresa,
        alias=fila.servicio.alias,
        codigo_suministro=fila.servicio.codigo_suministro,
        categoria=CategoriaBandeja.model_validate(fila.categoria, from_attributes=True),
        monto=deuda.monto,
        saldo=fila.saldo,
        moneda=deuda.moneda,
        estado=deuda.estado,
        fecha_vencimiento=deuda.fecha_vencimiento,
        en_ruta=deuda.estado in ESTADOS_EN_RUTA and deuda.pago_iniciado_por == usuario_id,
        pago_realizado=deuda.pago_realizado,
        pago_realizado_en=deuda.pago_realizado_en,
        comprobante_estado=fila.comprobante_estado,
    )


@router.get("")
def ver_ruta(db: SesionDb, usuario: UsuarioActual) -> RutaSalida:
    """Deudas por pagar en persona, agrupadas por lugar, con el total de cada grupo."""
    grupos = consultar_ruta(db, usuario)
    filas = [fila for grupo in grupos for fila in grupo.filas]
    return RutaSalida(
        grupos=[
            GrupoRutaSalida(
                lugar=grupo.lugar,
                items=[item_salida(fila, usuario.id) for fila in grupo.filas],
                totales=TotalesRuta(**grupo.totales),
            )
            for grupo in grupos
        ],
        totales=TotalesRuta(**totales_de(filas)),
    )


@router.post("/iniciar")
def iniciar(
    datos: IniciarRutaEntrada, db: SesionDb, usuario: UsuarioActual, origen: OrigenSolicitud
) -> IniciarRutaSalida:
    """Inicia el pago de las deudas elegidas; cada una tiene su propio resultado."""
    resultados = iniciar_ruta(db, usuario, datos.deudas, origen=origen)
    db.commit()
    return IniciarRutaSalida(
        resultados=[
            ResultadoDeudaSalida(
                deuda_id=r.deuda_id,
                resultado=r.resultado,
                codigo=r.codigo,
                mensaje=r.mensaje,
                repetido=r.repetido,
            )
            for r in resultados
        ],
        totales=TotalesRuta(**total_iniciado(resultados)),
    )
