"""Registro manual (H11, TASK-38) y listado (H36, TASK-45) de deudas. Gerente y asistente
registran y listan las deudas del gerente.

Errores del registro: 404 NO_ENCONTRADO (servicio inexistente, eliminado o de otro gerente), 403
SIN_PERMISO, 422 VALIDACION, 409 SERVICIO_DE_BAJA y 409 DUPLICADO con deuda_existente (ya hay
una deuda activa del servicio en ese periodo). Una deuda vencida se registra con la advertencia.
Errores del listado: 404 NO_ENCONTRADO (categoría o servicio ajeno o inexistente), 403
SIN_PERMISO y 422 VALIDACION con el parámetro en field. El detalle es de TASK-53.
"""

import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from app.core.dependencias import GerenteId, OrigenSolicitud, SesionDb, UsuarioActual
from app.core.errores import ErrorApi
from app.core.paginacion import ParametrosPagina
from app.schemas.bandeja import CategoriaBandeja
from app.schemas.deudas import (
    ESTADOS_DEUDA,
    AdvertenciasDeuda,
    DeudaEntrada,
    DeudaRegistradaSalida,
    ItemDeuda,
    ListadoDeudasSalida,
    Moneda,
    OrdenListado,
    Periodo,
)
from app.services.deudas import (
    FilaDeuda,
    FiltrosDeudas,
    listar_deudas,
    primer_dia,
    registrar_deuda,
    texto_periodo,
)

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
