"""Historial global del gerente (H34): listado y exportación con filtros iguales."""

import json
from datetime import date
from io import BytesIO
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from openpyxl import Workbook

from app.core.dependencias import SesionDb, SoloGerente
from app.core.errores import ErrorApi
from app.core.paginacion import Pagina, ParametrosPagina, paginar
from app.core.tiempo import zona_horaria
from app.models import Auditoria
from app.schemas.auditoria import RegistroAuditoriaSalida
from app.services.auditoria import FiltrosHistorial, consulta_historial_filtrado

router = APIRouter(prefix="/auditoria", tags=["auditoria"])
TIPO_EXCEL = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def obtener_filtros(
    usuario: Annotated[str | None, Query(max_length=150)] = None,
    accion: Annotated[str | None, Query(max_length=100)] = None,
    desde: date | None = None,
    hasta: date | None = None,
) -> FiltrosHistorial:
    usuario = usuario.strip() if usuario is not None else None
    accion = accion.strip() if accion is not None else None
    if usuario == "":
        raise ErrorApi(422, "VALIDACION", "El usuario no puede estar vacío.", "usuario")
    if accion == "":
        raise ErrorApi(422, "VALIDACION", "La acción no puede estar vacía.", "accion")
    if desde is not None and hasta is not None and desde > hasta:
        raise ErrorApi(
            422, "VALIDACION", "La fecha final debe ser igual o posterior a la inicial.", "hasta"
        )
    return FiltrosHistorial(usuario=usuario, accion=accion, desde=desde, hasta=hasta)


Filtros = Annotated[FiltrosHistorial, Depends(obtener_filtros)]


def salida(registro: Auditoria) -> RegistroAuditoriaSalida:
    return RegistroAuditoriaSalida(
        id=registro.id,
        gerente_id=registro.gerente_id,
        usuario_id=registro.usuario_id,
        usuario_nombre=registro.usuario_nombre,
        accion=registro.accion,
        entidad=registro.entidad,
        entidad_id=registro.entidad_id,
        detalle=registro.detalle,
        dispositivo=registro.dispositivo,
        ip=str(registro.ip) if registro.ip is not None else None,
        creado_en=registro.creado_en,
    )


@router.get("", response_model=Pagina[RegistroAuditoriaSalida])
def listar(
    db: SesionDb, gerente: SoloGerente, pagina: ParametrosPagina, filtros: Filtros
) -> Pagina[RegistroAuditoriaSalida]:
    resultado = paginar(db, consulta_historial_filtrado(gerente, filtros), pagina)
    return Pagina(
        items=[salida(registro) for registro in resultado.items],
        total=resultado.total,
        page=resultado.page,
    )


def texto_excel(valor: str | None) -> str:
    """Impide que un nombre o un User-Agent controlado por el cliente sea una fórmula."""
    if valor is None:
        return ""
    return "'" + valor if valor.lstrip().startswith(("=", "+", "-", "@")) else valor


@router.get("/exportar")
def exportar(db: SesionDb, gerente: SoloGerente, filtros: Filtros) -> Response:
    libro = Workbook(write_only=True)
    hoja = libro.create_sheet("Historial")
    hoja.append(
        (
            "Fecha (Lima)",
            "Usuario",
            "Acción",
            "Entidad",
            "ID entidad",
            "Detalle",
            "Dispositivo",
            "IP",
        )
    )
    for registro in db.scalars(consulta_historial_filtrado(gerente, filtros)):
        hoja.append(
            (
                registro.creado_en.astimezone(zona_horaria()).isoformat(),
                texto_excel(registro.usuario_nombre),
                texto_excel(registro.accion),
                texto_excel(registro.entidad),
                str(registro.entidad_id) if registro.entidad_id else "",
                texto_excel(json.dumps(registro.detalle, ensure_ascii=False, sort_keys=True)),
                texto_excel(registro.dispositivo),
                str(registro.ip) if registro.ip else "",
            )
        )
    archivo = BytesIO()
    libro.save(archivo)
    return Response(
        content=archivo.getvalue(),
        media_type=TIPO_EXCEL,
        headers={
            "Content-Disposition": 'attachment; filename="historial-auditoria.xlsx"',
            "Cache-Control": "no-store",
        },
    )
