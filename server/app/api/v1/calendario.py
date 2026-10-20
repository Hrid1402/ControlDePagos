"""Calendario de deudas y exportación iCalendar (H16, TASK-58)."""

import uuid
from datetime import date, timedelta

from fastapi import APIRouter, Response
from icalendar import Calendar, Event

from app.core.dependencias import GerenteId, SesionDb
from app.core.errores import ErrorApi
from app.core.tiempo import ahora_lima
from app.schemas.calendario import CalendarioSalida, DiaCalendario
from app.services.calendario import ESTADOS_CALENDARIO, ESTADOS_PENDIENTES, vencimientos

router = APIRouter(prefix="/calendario", tags=["calendario"])


def consultar(
    db: SesionDb,
    gerente_id: GerenteId,
    desde: date,
    hasta: date,
    categoria: uuid.UUID | None = None,
    estado: str | None = None,
) -> CalendarioSalida:
    if desde > hasta:
        raise ErrorApi(422, "VALIDACION", "La fecha inicial debe ser anterior a la final.", "desde")
    if estado is not None and estado not in ESTADOS_CALENDARIO:
        raise ErrorApi(422, "VALIDACION", "El estado no es válido.", "estado")
    return CalendarioSalida(
        dias=[
            DiaCalendario.model_validate(dia)
            for dia in vencimientos(db, gerente_id, desde, hasta, categoria, estado)
        ]
    )


@router.get("", response_model=CalendarioSalida)
def listar(
    db: SesionDb,
    gerente_id: GerenteId,
    desde: date,
    hasta: date,
    categoria: uuid.UUID | None = None,
    estado: str | None = None,
) -> CalendarioSalida:
    return consultar(db, gerente_id, desde, hasta, categoria, estado)


@router.get("/exportar.ics")
def exportar(
    db: SesionDb,
    gerente_id: GerenteId,
    desde: date,
    hasta: date,
    categoria: uuid.UUID | None = None,
    estado: str | None = None,
) -> Response:
    calendario = consultar(db, gerente_id, desde, hasta, categoria, estado)
    archivo = Calendar()
    archivo.add("prodid", "-//Control de Pagos//Calendario//ES")
    archivo.add("version", "2.0")
    archivo.add("calscale", "GREGORIAN")
    for dia in calendario.dias:
        for deuda in dia.deudas:
            if deuda.estado not in ESTADOS_PENDIENTES and deuda.estado != "vencida":
                continue
            evento = Event()
            evento.add("uid", f"deuda-{deuda.id}@control-de-pagos")
            evento.add("dtstamp", ahora_lima())
            evento.add("dtstart", deuda.fecha_vencimiento)
            evento.add("dtend", deuda.fecha_vencimiento + timedelta(days=1))
            evento.add("summary", deuda.nombre)
            archivo.add_component(evento)
    return Response(
        content=archivo.to_ical(),
        media_type="text/calendar; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="calendario.ics"'},
    )
