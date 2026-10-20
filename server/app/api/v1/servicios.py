"""Servicios del gerente (H10): lista, detalle, registro, edición, baja y reactivación.

Gerente y asistente listan, registran y editan; dar de baja y reactivar son solo del gerente.
Errores: 404 NO_ENCONTRADO (servicio, categoría o empresa inexistente o de otro gerente),
403 SIN_PERMISO, 422 VALIDACION, 409 DUPLICADO (misma empresa y código), 409 SERVICIO_DE_BAJA
y 409 CONFLICTO (reactivar un servicio activo).
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from app.core.dependencias import (
    GerenteId,
    OrigenSolicitud,
    SesionDb,
    SoloGerente,
    UsuarioActual,
)
from app.core.paginacion import Pagina, ParametrosPagina, paginar
from app.schemas.servicios import (
    AdvertenciasServicio,
    CategoriaServicio,
    FiltroEstado,
    ServicioBajaSalida,
    ServicioDetalleSalida,
    ServicioEditadoSalida,
    ServicioEntrada,
    ServicioSalida,
)
from app.services.servicios import (
    FilaServicio,
    FiltrosServicios,
    consulta_servicios,
    contar_deudas_pendientes,
    crear_servicio,
    dar_de_baja,
    editar_servicio,
    fila_de,
    filas_de,
    reactivar_servicio,
    servicio_propio,
)

router = APIRouter(prefix="/servicios", tags=["servicios"])


def obtener_filtros(
    q: Annotated[str | None, Query(max_length=100)] = None,
    categoria_id: uuid.UUID | None = None,
    estado: FiltroEstado = "activo",
) -> FiltrosServicios:
    return FiltrosServicios(q=(q or "").strip() or None, categoria_id=categoria_id, estado=estado)


Filtros = Annotated[FiltrosServicios, Depends(obtener_filtros)]


def campos(fila: FilaServicio) -> dict[str, object]:
    servicio = fila.servicio
    return {
        "id": servicio.id,
        "categoria": CategoriaServicio.model_validate(fila.categoria, from_attributes=True),
        "empresa_id": servicio.empresa_id,
        "empresa": fila.nombre_empresa,
        "empresa_manual": servicio.empresa_id is None,
        "codigo_suministro": servicio.codigo_suministro,
        "titular": servicio.titular,
        "alias": servicio.alias,
        "lugar_pago": servicio.lugar_pago,
        "notas": servicio.notas,
        "estado": servicio.estado,
        "creado_por": servicio.creado_por,
        "creado_en": servicio.creado_en,
        "actualizado_en": servicio.actualizado_en,
    }


@router.get("", response_model=Pagina[ServicioSalida])
def listar(
    db: SesionDb, gerente_id: GerenteId, pagina: ParametrosPagina, filtros: Filtros
) -> Pagina[ServicioSalida]:
    resultado = paginar(db, consulta_servicios(db, gerente_id, filtros), pagina)
    return Pagina(
        items=[ServicioSalida.model_validate(campos(f)) for f in filas_de(db, resultado.items)],
        total=resultado.total,
        page=resultado.page,
    )


@router.get("/{servicio_id}", response_model=ServicioDetalleSalida)
def detalle(servicio_id: uuid.UUID, db: SesionDb, gerente_id: GerenteId) -> ServicioDetalleSalida:
    servicio = servicio_propio(db, servicio_id, gerente_id)
    return ServicioDetalleSalida.model_validate(
        campos(fila_de(db, servicio))
        | {"deudas_pendientes": contar_deudas_pendientes(db, servicio.id)}
    )


@router.post("", response_model=ServicioSalida, status_code=status.HTTP_201_CREATED)
def crear(
    datos: ServicioEntrada,
    db: SesionDb,
    usuario: UsuarioActual,
    gerente_id: GerenteId,
    origen: OrigenSolicitud,
) -> ServicioSalida:
    fila = crear_servicio(db, usuario, gerente_id, datos, origen)
    db.commit()
    return ServicioSalida.model_validate(campos(fila))


@router.put("/{servicio_id}", response_model=ServicioEditadoSalida)
def editar(
    servicio_id: uuid.UUID,
    datos: ServicioEntrada,
    db: SesionDb,
    usuario: UsuarioActual,
    gerente_id: GerenteId,
    origen: OrigenSolicitud,
) -> ServicioEditadoSalida:
    """Si cambia el código, advertencias informa las deudas pendientes (CA07)."""
    edicion = editar_servicio(db, usuario, gerente_id, servicio_id, datos, origen)
    db.commit()
    advertencias = AdvertenciasServicio(
        codigo_cambiado=edicion.codigo_cambiado, deudas_pendientes=edicion.deudas_pendientes
    )
    return ServicioEditadoSalida.model_validate(
        campos(edicion.fila) | {"advertencias": advertencias}
    )


@router.post("/{servicio_id}/baja", response_model=ServicioBajaSalida)
def baja(
    servicio_id: uuid.UUID, db: SesionDb, gerente: SoloGerente, origen: OrigenSolicitud
) -> ServicioBajaSalida:
    resultado = dar_de_baja(db, gerente, servicio_id, origen)
    db.commit()
    return ServicioBajaSalida.model_validate(
        campos(resultado.fila)
        | {
            "recurrencias_desactivadas": resultado.recurrencias_desactivadas,
            "deudas_pendientes": resultado.deudas_pendientes,
        }
    )


@router.post("/{servicio_id}/reactivar", response_model=ServicioSalida)
def reactivar(
    servicio_id: uuid.UUID, db: SesionDb, gerente: SoloGerente, origen: OrigenSolicitud
) -> ServicioSalida:
    fila = reactivar_servicio(db, gerente, servicio_id, origen)
    db.commit()
    return ServicioSalida.model_validate(campos(fila))
