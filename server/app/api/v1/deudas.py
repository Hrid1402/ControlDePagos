"""Registro manual (H11, TASK-38) y listado (H36, TASK-45) de deudas. Gerente y asistente
registran y listan las deudas del gerente.

Errores del registro: 404 NO_ENCONTRADO (servicio inexistente, eliminado o de otro gerente), 403
SIN_PERMISO, 422 VALIDACION, 409 SERVICIO_DE_BAJA y 409 DUPLICADO con deuda_existente (ya hay
una deuda activa del servicio en ese periodo). Una deuda vencida se registra con la advertencia.
Errores del listado: 404 NO_ENCONTRADO (categoría o servicio ajeno o inexistente), 403
SIN_PERMISO y 422 VALIDACION con el parámetro en field.
Detalle (H17, TASK-53): 404 NO_ENCONTRADO si la deuda no existe o es de otro gerente.
Edición y anulación (TASK-40): responden el detalle actualizado. 409 ESTADO_NO_PERMITIDO (pagada
o anulada), PAGO_EN_CURSO, CON_ABONOS u ORDEN_ABIERTA; anular es solo del gerente (403).
"""

import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, File, Query, UploadFile, status

from app.core.dependencias import (
    GerenteId,
    OrigenSolicitud,
    SesionDb,
    SoloGerente,
    UsuarioActual,
)
from app.core.errores import ErrorApi
from app.core.paginacion import ParametrosPagina
from app.schemas.bandeja import CategoriaBandeja, EnProcesoBandeja, OrdenUrgenteBandeja
from app.schemas.detalle_deuda import (
    Actor,
    CambioMonto,
    ComprobanteDeLaDeuda,
    DetalleDeudaSalida,
    EventoDeuda,
    ServicioDetalle,
)
from app.schemas.deudas import (
    ESTADOS_DEUDA,
    AdvertenciasDeuda,
    AnulacionEntrada,
    DeudaEdicion,
    DeudaEntrada,
    DeudaRegistradaSalida,
    ItemDeuda,
    ListadoDeudasSalida,
    Moneda,
    OrdenListado,
    Periodo,
)
from app.services.archivos import (
    confirmar_con_archivo,
    eliminar_privado,
    enlace_firmado,
    validar_archivo,
)
from app.services.auditoria import nombre_de
from app.services.detalle_deuda import DetalleDeuda, obtener_detalle
from app.services.deudas import (
    FilaDeuda,
    FiltrosDeudas,
    listar_deudas,
    primer_dia,
    registrar_deuda,
    texto_periodo,
)
from app.services.edicion_deudas import adjuntar_recibo, anular_deuda, editar_deuda

router = APIRouter(prefix="/deudas", tags=["deudas"])


def obtener_filtros(
    q: Annotated[str | None, Query(max_length=100)] = None,
    estado: Annotated[list[str] | None, Query()] = None,
    vencida: bool | None = None,
    categoria: uuid.UUID | None = None,
    servicio: uuid.UUID | None = None,
    moneda: Moneda | None = None,
    mes: Annotated[Periodo | None, Query()] = None,
    vence_desde: date | None = None,
    vence_hasta: date | None = None,
    orden: OrdenListado = "vencimiento",
) -> FiltrosDeudas:
    """estado se repite para pedir varios (?estado=pendiente&estado=pagada_parcial). Se valida
    aquí para que el error nombre el parámetro y no su posición en la lista."""
    estados = tuple(dict.fromkeys(estado or ()))
    if any(e not in ESTADOS_DEUDA for e in estados):
        raise ErrorApi(422, "VALIDACION", "El estado no es válido.", "estado")
    if vence_desde is not None and vence_hasta is not None and vence_desde > vence_hasta:
        raise ErrorApi(
            422, "VALIDACION", "La fecha inicial debe ser anterior a la final.", "vence_desde"
        )
    return FiltrosDeudas(
        q=(q or "").strip() or None,
        estados=estados,
        vencida=vencida,
        categoria_id=categoria,
        servicio_id=servicio,
        moneda=moneda,
        mes=primer_dia(mes) if mes is not None else None,
        vence_desde=vence_desde,
        vence_hasta=vence_hasta,
        orden=orden,
    )


Filtros = Annotated[FiltrosDeudas, Depends(obtener_filtros)]


def item_salida(fila: FilaDeuda) -> ItemDeuda:
    deuda, servicio = fila.deuda, fila.servicio
    return ItemDeuda(
        id=deuda.id,
        servicio_id=servicio.id,
        empresa=fila.empresa,
        alias=servicio.alias,
        codigo_suministro=servicio.codigo_suministro,
        categoria=CategoriaBandeja.model_validate(fila.categoria, from_attributes=True),
        periodo=texto_periodo(deuda.periodo),
        monto=deuda.monto,
        moneda=deuda.moneda,
        pagado=fila.pagado,
        saldo=fila.saldo,
        monto_proyectado=fila.proyeccion,
        fecha_vencimiento=deuda.fecha_vencimiento,
        vencida=fila.vencida,
        estado=deuda.estado,
        numero_recibo=deuda.numero_recibo,
    )


@router.get("")
def listar(
    db: SesionDb, gerente_id: GerenteId, parametros: ParametrosPagina, filtros: Filtros
) -> ListadoDeudasSalida:
    """Página de deudas del gerente y totales por moneda de todo el filtro."""
    listado = listar_deudas(db, gerente_id, filtros, parametros)
    return ListadoDeudasSalida(
        items=[item_salida(fila) for fila in listado.filas],
        total=listado.total,
        page=parametros.page,
        totales=listado.totales,
    )


@router.post("", response_model=DeudaRegistradaSalida, status_code=status.HTTP_201_CREATED)
def registrar(
    datos: DeudaEntrada,
    db: SesionDb,
    usuario: UsuarioActual,
    gerente_id: GerenteId,
    origen: OrigenSolicitud,
) -> DeudaRegistradaSalida:
    registro = registrar_deuda(db, usuario, gerente_id, datos, origen)
    db.commit()
    deuda = registro.deuda
    # El registro manual exige monto positivo: nunca queda esperando recibo.
    assert deuda.monto is not None
    return DeudaRegistradaSalida(
        id=deuda.id,
        servicio_id=deuda.servicio_id,
        periodo=texto_periodo(deuda.periodo),
        monto=deuda.monto,
        moneda=deuda.moneda,
        fecha_vencimiento=deuda.fecha_vencimiento,
        numero_recibo=deuda.numero_recibo,
        estado=deuda.estado,
        origen=deuda.origen,
        creado_por=deuda.creado_por,
        creado_en=deuda.creado_en,
        advertencias=AdvertenciasDeuda(vencida=registro.vencida),
    )


def detalle_salida(detalle: DetalleDeuda) -> DetalleDeudaSalida:
    deuda, servicio = detalle.deuda, detalle.servicio
    iniciador, orden = detalle.iniciador, detalle.orden
    return DetalleDeudaSalida(
        id=deuda.id,
        servicio=ServicioDetalle(
            id=servicio.id,
            empresa=detalle.empresa,
            alias=servicio.alias,
            codigo_suministro=servicio.codigo_suministro,
            titular=servicio.titular,
            lugar_pago=servicio.lugar_pago,
            notas=servicio.notas,
        ),
        categoria=CategoriaBandeja.model_validate(detalle.categoria, from_attributes=True),
        periodo=texto_periodo(deuda.periodo),
        estado=deuda.estado,
        origen=deuda.origen,
        moneda=deuda.moneda,
        monto=deuda.monto,
        pagado=detalle.pagado,
        saldo=detalle.saldo,
        monto_proyectado=detalle.proyeccion,
        vencida=detalle.vencida,
        fecha_emision=deuda.fecha_emision,
        fecha_vencimiento=deuda.fecha_vencimiento,
        fecha_estimada=deuda.fecha_estimada,
        fecha_corte=deuda.fecha_corte,
        pago_minimo=deuda.pago_minimo,
        pago_total=deuda.pago_total,
        numero_recibo=deuda.numero_recibo,
        recibo_enlace=enlace_firmado(deuda.recibo_url) if deuda.recibo_url else None,
        cuota_numero=deuda.cuota_numero,
        cuotas_total=detalle.cuotas_total,
        en_proceso=(
            EnProcesoBandeja(
                usuario_id=iniciador.id,
                rol=iniciador.rol,
                nombre=nombre_de(iniciador),
                desde=deuda.pago_iniciado_en,
            )
            if iniciador is not None
            else None
        ),
        orden_urgente=(
            OrdenUrgenteBandeja(id=orden.id, estado=orden.estado, plazo=orden.plazo)
            if orden is not None
            else None
        ),
        creado_en=deuda.creado_en,
        comprobantes=[
            ComprobanteDeLaDeuda(
                id=f.comprobante.id,
                estado=f.comprobante.estado,
                motivo_codigo=f.comprobante.motivo_codigo,
                observacion=f.comprobante.datos_extraidos.get("observacion"),
                monto=f.comprobante.monto,
                monto_aplicado=f.monto_aplicado,
                moneda=f.comprobante.moneda,
                subido_por=f.subido_por,
                creado_en=f.comprobante.creado_en,
                reemplaza_a_id=f.comprobante.reemplaza_a_id,
            )
            for f in detalle.comprobantes
        ],
        historial_montos=[
            CambioMonto(
                monto_anterior=f.cambio.monto_anterior,
                monto_nuevo=f.cambio.monto_nuevo,
                origen=f.cambio.origen,
                usuario=f.usuario,
                creado_en=f.cambio.creado_en,
            )
            for f in detalle.historial
        ],
        linea_tiempo=[
            EventoDeuda(
                tipo=e.tipo,
                fecha=e.fecha,
                actor=Actor(nombre=e.actor[0], rol=e.actor[1]) if e.actor else None,
                detalle=e.detalle,
            )
            for e in detalle.linea_tiempo
        ],
        acciones=[a.value for a in detalle.acciones],
    )


@router.get("/{deuda_id}")
def ver(deuda_id: uuid.UUID, db: SesionDb, usuario: UsuarioActual) -> DetalleDeudaSalida:
    """Detalle de la deuda con sus comprobantes, historial, línea de tiempo y acciones."""
    return detalle_salida(obtener_detalle(db, usuario, deuda_id))


@router.put("/{deuda_id}")
def editar(
    deuda_id: uuid.UUID,
    datos: DeudaEdicion,
    db: SesionDb,
    usuario: UsuarioActual,
    origen: OrigenSolicitud,
) -> DetalleDeudaSalida:
    editar_deuda(db, usuario, deuda_id, datos, origen=origen)
    db.commit()
    return detalle_salida(obtener_detalle(db, usuario, deuda_id))


@router.post("/{deuda_id}/anular")
def anular(
    deuda_id: uuid.UUID,
    db: SesionDb,
    gerente: SoloGerente,
    origen: OrigenSolicitud,
    entrada: AnulacionEntrada | None = None,
) -> DetalleDeudaSalida:
    anular_deuda(db, gerente, deuda_id, entrada.motivo if entrada else None, origen=origen)
    db.commit()
    return detalle_salida(obtener_detalle(db, gerente, deuda_id))


@router.post("/{deuda_id}/recibo")
def subir_recibo(
    deuda_id: uuid.UUID,
    archivo: Annotated[UploadFile, File()],
    db: SesionDb,
    usuario: UsuarioActual,
    origen: OrigenSolicitud,
) -> DetalleDeudaSalida:
    """Adjunta o reemplaza el recibo (CA08): PDF, JPG o PNG de hasta 10 MB, privado."""
    deuda, anterior = adjuntar_recibo(
        db, usuario, deuda_id, validar_archivo(archivo), origen=origen
    )
    confirmar_con_archivo(db, deuda.recibo_url or "")
    if anterior:
        eliminar_privado(anterior)
    return detalle_salida(obtener_detalle(db, usuario, deuda_id))
