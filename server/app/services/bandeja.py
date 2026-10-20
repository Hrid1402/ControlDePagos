"""Bandeja de la asistente (H15): prioridad, pestañas con contadores, fijar y recordar mañana.

Nivel de prioridad, en este orden de evaluación, con su etiqueta como código:
0 orden_urgente (orden abierta: enviada, vista o aceptada), 1 fijada, 2 vencida, 3 vence_hoy,
4 tarjeta (categoría de tipo tarjeta) y 5 proxima. Desempate estable: nivel, plazo de la orden,
vencimiento e id. Se calcula en SQL para ordenar y paginar sin cargar todas las deudas.

Pestañas, según el estado de la deuda y el último comprobante del intento actual (subido desde
pago_iniciado_en):
- Por pagar: pendiente, pagada_parcial, esperando_aprobacion, con_problema, o en_proceso sin
  comprobante del intento.
- Por validar: por_validar, o en_proceso con el último comprobante del intento todavía activo.
- Rechazadas: en_proceso con el último comprobante del intento rechazado.
esperando_recibo, pagada y anulada quedan fuera. Un reemplazo es un comprobante más reciente:
la deuda pasa sola de Rechazadas a Por validar.

Recordar mañana oculta la deuda hasta las 08:00 del día siguiente en Lima. No hay job: la
consulta compara oculta_hasta con la hora actual. Una orden urgente nunca queda oculta y una
deuda que alguien empezó a pagar tampoco. Los contadores siguen la misma regla de visibilidad y
el mismo filtro de categoría que la lista, así que coinciden con su total.

Hoy y ahora se calculan en la zona del sistema y llegan a la consulta como parámetros: la base
guarda UTC y su CURRENT_DATE no es la fecha de Lima por la noche.
"""

import uuid
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import ColumnElement, ScalarSelect, Select, and_, case, func, or_, select
from sqlalchemy.orm import Session, aliased

from app.core.dependencias import Origen
from app.core.errores import ErrorApi
from app.core.paginacion import Paginacion
from app.core.tiempo import ahora_lima, hoy_de, zona_horaria
from app.models import (
    Categoria,
    Comprobante,
    ComprobanteDeuda,
    Deuda,
    Empresa,
    OrdenPago,
    Servicio,
    Usuario,
)
from app.services.auditoria import Accion, registrar_auditoria
from app.services.pagos import bloquear_deuda
from app.services.saldo import ESTADOS_COMPROBANTE_ACTIVO, aplicado_validado, vencida

ESTADOS_POR_PAGAR = ("pendiente", "pagada_parcial", "esperando_aprobacion", "con_problema")
# Solo se pospone lo que nadie está pagando: ocultar un intento en curso haría perderlo de vista.
ESTADOS_POSPONIBLES = ("pendiente", "pagada_parcial")
# Las mismas que cubre uq_orden_pago_abierta.
ESTADOS_ORDEN_ABIERTA = ("enviada", "vista", "aceptada")
HORA_RECORDAR = time(8, 0)


class Pestana(StrEnum):
    POR_PAGAR = "por_pagar"
    POR_VALIDAR = "por_validar"
    RECHAZADAS = "rechazadas"


class Etiqueta(StrEnum):
    """Motivo de la prioridad. Su posición es el nivel; el texto lo pone el frontend."""

    ORDEN_URGENTE = "orden_urgente"
    FIJADA = "fijada"
    VENCIDA = "vencida"
    VENCE_HOY = "vence_hoy"
    TARJETA = "tarjeta"
    PROXIMA = "proxima"


ETIQUETAS = list(Etiqueta)


@dataclass(frozen=True)
class FilaBandeja:
    deuda: Deuda
    servicio: Servicio
    categoria: Categoria
    empresa: str | None
    orden: OrdenPago | None
    iniciador: Usuario | None
    saldo: Decimal | None
    nivel: int
    comprobante_estado: str | None
    dias_restantes: int

    @property
    def etiqueta(self) -> Etiqueta:
        return ETIQUETAS[self.nivel]


@dataclass(frozen=True)
class Bandeja:
    filas: list[FilaBandeja]
    contadores: dict[Pestana, int]
    pestana: Pestana

    @property
    def total(self) -> int:
        return self.contadores[self.pestana]


def manana_a_las_ocho(ahora: datetime) -> datetime:
    """08:00 del día siguiente en la zona del sistema, aunque se pida pasada la medianoche."""
    return datetime.combine(hoy_de(ahora) + timedelta(days=1), HORA_RECORDAR, zona_horaria())


def estado_comprobante_intento() -> ScalarSelect[str]:
    """Estado del último comprobante subido para el intento en curso de la deuda. Un comprobante
    de un intento anterior, por ejemplo uno rechazado antes de cancelar el inicio, no cuenta."""
    return (
        select(Comprobante.estado)
        .join(ComprobanteDeuda, ComprobanteDeuda.comprobante_id == Comprobante.id)
        .where(
            ComprobanteDeuda.deuda_id == Deuda.id,
            Comprobante.creado_en >= Deuda.pago_iniciado_en,
        )
        .order_by(Comprobante.creado_en.desc(), Comprobante.id.desc())
        .limit(1)
        .correlate(Deuda)
        .scalar_subquery()
    )


def pestana_de(comprobante: ColumnElement[str]) -> ColumnElement[str | None]:
    en_proceso = Deuda.estado == "en_proceso"
    return case(
        (Deuda.estado.in_(ESTADOS_POR_PAGAR), Pestana.POR_PAGAR.value),
        (Deuda.estado == "por_validar", Pestana.POR_VALIDAR.value),
        (and_(en_proceso, comprobante.is_(None)), Pestana.POR_PAGAR.value),
        (and_(en_proceso, comprobante == "rechazado"), Pestana.RECHAZADAS.value),
        (and_(en_proceso, comprobante.in_(ESTADOS_COMPROBANTE_ACTIVO)), Pestana.POR_VALIDAR.value),
        else_=None,
    )


def nivel_de(hoy: date) -> ColumnElement[int]:
    return case(
        (OrdenPago.id.is_not(None), 0),
        (Deuda.fijada, 1),
        (vencida(hoy), 2),
        (Deuda.fecha_vencimiento == hoy, 3),
        (Categoria.tipo == "tarjeta", 4),
        else_=5,
    )


def visible(ahora: datetime) -> ColumnElement[bool]:
    return or_(
        OrdenPago.id.is_not(None),
        Deuda.oculta_hasta.is_(None),
        Deuda.oculta_hasta <= ahora,
        Deuda.estado.not_in(ESTADOS_POSPONIBLES),
    )


def con_filtros[*T](
    consulta: Select[*T], gerente_id: uuid.UUID, categoria_id: uuid.UUID | None, ahora: datetime
) -> Select[*T]:
    """Deudas visibles del gerente, con su servicio, categoría y orden abierta si la tiene."""
    consulta = (
        consulta.join(Servicio, Servicio.id == Deuda.servicio_id)
        .join(Categoria, Categoria.id == Servicio.categoria_id)
        .outerjoin(
            OrdenPago,
            and_(OrdenPago.deuda_id == Deuda.id, OrdenPago.estado.in_(ESTADOS_ORDEN_ABIERTA)),
        )
        .where(Deuda.gerente_id == gerente_id, visible(ahora))
    )
    if categoria_id is not None:
        consulta = consulta.where(Servicio.categoria_id == categoria_id)
    return consulta


def validar_categoria(db: Session, categoria_id: uuid.UUID, gerente_id: uuid.UUID) -> None:
    """Una categoría ajena o inexistente es un error: con una lista vacía la pantalla diría
    «Todo al día»."""
    categoria = db.get(Categoria, categoria_id)
    if categoria is None or categoria.gerente_id != gerente_id:
        raise ErrorApi(404, "NO_ENCONTRADO", "No se encontró la categoría.", "categoria")


def contar(
    db: Session, gerente_id: uuid.UUID, categoria_id: uuid.UUID | None, ahora: datetime
) -> dict[Pestana, int]:
    """Los tres contadores en una sola consulta, sin traer las deudas."""
    pestana = pestana_de(estado_comprobante_intento())
    consulta = select(
        *(func.count().filter(pestana == p.value).label(p.value) for p in Pestana)
    ).select_from(Deuda)
    fila = db.execute(con_filtros(consulta, gerente_id, categoria_id, ahora)).one()
    return {p: getattr(fila, p.value) for p in Pestana}


def consultar_bandeja(
    db: Session,
    gerente_id: uuid.UUID,
    pestana: Pestana,
    parametros: Paginacion,
    categoria_id: uuid.UUID | None = None,
    ahora: datetime | None = None,
) -> Bandeja:
    momento = ahora or ahora_lima()
    hoy = hoy_de(momento)
    if categoria_id is not None:
        validar_categoria(db, categoria_id, gerente_id)
    contadores = contar(db, gerente_id, categoria_id, momento)

    comprobante = estado_comprobante_intento()
    nivel = nivel_de(hoy)
    iniciador = aliased(Usuario)
    consulta = select(
        Deuda,
        Servicio,
        Categoria,
        OrdenPago,
        iniciador,
        func.coalesce(Empresa.nombre, Servicio.empresa_nombre),
        Deuda.monto - aplicado_validado(Deuda.id),
        nivel,
        comprobante,
    ).select_from(Deuda)
    consulta = (
        con_filtros(consulta, gerente_id, categoria_id, momento)
        .outerjoin(Empresa, Empresa.id == Servicio.empresa_id)
        .outerjoin(iniciador, iniciador.id == Deuda.pago_iniciado_por)
        .where(pestana_de(comprobante) == pestana.value)
        .order_by(nivel, OrdenPago.plazo.asc().nulls_last(), Deuda.fecha_vencimiento, Deuda.id)
        .offset(parametros.offset)
        .limit(parametros.size)
    )
    filas = [
        FilaBandeja(
            deuda=deuda,
            servicio=servicio,
            categoria=categoria,
            empresa=empresa,
            orden=orden,
            iniciador=usuario,
            saldo=saldo,
            nivel=nivel_fila,
            comprobante_estado=estado,
            dias_restantes=(deuda.fecha_vencimiento - hoy).days,
        )
        for deuda, servicio, categoria, orden, usuario, empresa, saldo, nivel_fila, estado in (
            db.execute(consulta)
        )
    ]
    return Bandeja(filas=filas, contadores=contadores, pestana=pestana)


def pestana_actual(db: Session, deuda: Deuda) -> Pestana | None:
    valor = db.scalar(select(pestana_de(estado_comprobante_intento())).where(Deuda.id == deuda.id))
    return Pestana(valor) if valor is not None else None


def tiene_orden_abierta(db: Session, deuda_id: uuid.UUID) -> bool:
    return (
        db.scalar(
            select(OrdenPago.id).where(
                OrdenPago.deuda_id == deuda_id, OrdenPago.estado.in_(ESTADOS_ORDEN_ABIERTA)
            )
        )
        is not None
    )


def fijar(
    db: Session, usuario: Usuario, deuda_id: uuid.UUID, fijada: bool, *, origen: Origen
) -> Deuda:
    """Fija o desfija la deuda. Solo cambia en Por pagar, la única pestaña que ordena por
    prioridad; repetir el mismo valor no genera otro evento de auditoría."""
    if usuario.gerente_id is None:
        raise ErrorApi(403, "SIN_PERMISO", "No tienes permiso para realizar esta acción.")
    deuda = bloquear_deuda(db, deuda_id, usuario.gerente_id)
    if pestana_actual(db, deuda) != Pestana.POR_PAGAR:
        raise ErrorApi(409, "ESTADO_NO_PERMITIDO", "Solo se puede fijar una deuda por pagar.")
    if deuda.fijada != fijada:
        deuda.fijada = fijada
        registrar_auditoria(
            db, usuario, Accion.DEUDA_FIJADA, "deuda", deuda.id, {"fijada": fijada}, origen=origen
        )
    return deuda


def recordar_manana(
    db: Session,
    usuario: Usuario,
    deuda_id: uuid.UUID,
    *,
    origen: Origen,
    ahora: datetime | None = None,
) -> Deuda:
    """Oculta la deuda hasta las 08:00 del día siguiente. Con una orden abierta responde 409:
    posponerla no tendría efecto. Si la orden llega después, la consulta la muestra igual."""
    if usuario.gerente_id is None:
        raise ErrorApi(403, "SIN_PERMISO", "No tienes permiso para realizar esta acción.")
    deuda = bloquear_deuda(db, deuda_id, usuario.gerente_id)
    if tiene_orden_abierta(db, deuda.id):
        raise ErrorApi(
            409,
            "ORDEN_URGENTE_ACTIVA",
            "La deuda tiene una orden urgente del gerente; no se puede posponer.",
        )
    if deuda.estado not in ESTADOS_POSPONIBLES:
        raise ErrorApi(
            409, "ESTADO_NO_PERMITIDO", "Solo se puede posponer una deuda pendiente de pago."
        )
    hasta = manana_a_las_ocho(ahora or ahora_lima())
    if deuda.oculta_hasta != hasta:
        deuda.oculta_hasta = hasta
        registrar_auditoria(
            db,
            usuario,
            Accion.DEUDA_POSPUESTA,
            "deuda",
            deuda.id,
            {"oculta_hasta": hasta},
            origen=origen,
        )
    return deuda
