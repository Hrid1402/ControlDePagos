"""Ruta de pagos presenciales (H23): deudas agrupadas por lugar de pago e inicio en lote.

La ruta es una consulta, no una tabla. Entra lo que la persona puede salir a pagar:
- Deudas pendientes o pagadas en parte, con saldo.
- Las que ella misma está pagando: en proceso, declaradas o no (CA03), y por validar con su voucher
  subido, hasta que el gerente lo valide (TASK-80 distingue declarado de validado).
- Las que esperan la aprobación que ella pidió, para que sepa por qué no puede iniciarlas.
No entran las que paga otra persona, ni banca móvil, que en este sprint también es Yape (CA05).
Las deudas sin lugar registrado van en su propio grupo, al final.

Iniciar en lote reutiliza iniciar_pago de TASK-75 deuda por deuda, cada una en su propio
savepoint: una deuda en conflicto no deshace las demás y ninguna se omite en silencio. Las deudas
se procesan en orden de id, así dos lotes simultáneos bloquean en el mismo orden.
"""

import uuid
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import ColumnElement, and_, func, or_, select
from sqlalchemy.orm import Session

from app.core.dependencias import Origen, gerente_de
from app.core.errores import ErrorApi
from app.models import Categoria, Deuda, Empresa, Servicio, SolicitudAprobacion, Usuario
from app.services.bandeja import estado_comprobante_intento
from app.services.pagos import ESTADOS_INICIABLES, ResultadoInicio, iniciar_pago, sin_permiso
from app.services.saldo import aplicado_validado

# Orden de los grupos: el de la tabla de lugares de servicios, sin banca móvil.
LUGARES_RUTA = ("agente_bcp", "agente_kasnet", "ventanilla_empresa", "otro")
EXCLUIDOS = ("banca_movil",)
MONEDAS = ("PEN", "USD")
MAXIMO_LOTE = 50
# Estados de una deuda que la persona ya tiene en su ruta.
ESTADOS_EN_RUTA = ("en_proceso", "por_validar")


class ResultadoLote(StrEnum):
    INICIADA = "iniciada"
    REQUIERE_APROBACION = "requiere_aprobacion"
    CONFLICTO = "conflicto"


@dataclass(frozen=True)
class FilaRuta:
    deuda: Deuda
    servicio: Servicio
    categoria: Categoria
    empresa: str | None
    saldo: Decimal
    comprobante_estado: str | None


@dataclass(frozen=True)
class GrupoRuta:
    lugar: str | None
    filas: list[FilaRuta]

    @property
    def totales(self) -> dict[str, Decimal]:
        """Lo que hay que llevar si se paga todo el grupo, por moneda y sin convertir."""
        return totales_de(self.filas)


@dataclass(frozen=True)
class ResultadoDeuda:
    deuda_id: uuid.UUID
    resultado: ResultadoLote
    codigo: str | None = None
    mensaje: str | None = None
    repetido: bool = False
    saldo: Decimal | None = None
    moneda: str | None = None


def totales_de(filas: list[FilaRuta]) -> dict[str, Decimal]:
    totales = {moneda: Decimal("0.00") for moneda in MONEDAS}
    for fila in filas:
        totales[fila.deuda.moneda] += fila.saldo
    return totales


def en_la_ruta(usuario: Usuario) -> ColumnElement[bool]:
    """Condición de las deudas que la persona puede pagar o ya está pagando."""
    pidio_aprobacion = (
        select(SolicitudAprobacion.id)
        .where(
            SolicitudAprobacion.deuda_id == Deuda.id,
            SolicitudAprobacion.estado == "pendiente",
            SolicitudAprobacion.asistente_id == usuario.id,
        )
        .correlate(Deuda)
        .exists()
    )
    return or_(
        Deuda.estado.in_(ESTADOS_INICIABLES),
        and_(Deuda.estado.in_(ESTADOS_EN_RUTA), Deuda.pago_iniciado_por == usuario.id),
        and_(Deuda.estado == "esperando_aprobacion", pidio_aprobacion),
    )


def consultar_ruta(db: Session, usuario: Usuario) -> list[GrupoRuta]:
    """Grupos por lugar de pago, en el orden de LUGARES_RUTA y sin lugar al final. Dentro de
    cada grupo, por vencimiento e id."""
    gerente_id = gerente_de(usuario)
    if gerente_id is None:
        raise sin_permiso()
    saldo = Deuda.monto - aplicado_validado(Deuda.id)
    consulta = (
        select(
            Deuda,
            Servicio,
            Categoria,
            func.coalesce(Empresa.nombre, Servicio.empresa_nombre),
            saldo,
            estado_comprobante_intento(),
        )
        .join(Servicio, Servicio.id == Deuda.servicio_id)
        .join(Categoria, Categoria.id == Servicio.categoria_id)
        .outerjoin(Empresa, Empresa.id == Servicio.empresa_id)
        .where(
            Deuda.gerente_id == gerente_id,
            Deuda.monto.is_not(None),
            saldo > 0,
            en_la_ruta(usuario),
            or_(Servicio.lugar_pago.is_(None), Servicio.lugar_pago.not_in(EXCLUIDOS)),
        )
        .order_by(Deuda.fecha_vencimiento, Deuda.id)
    )
    grupos: dict[str | None, list[FilaRuta]] = {}
    for deuda, servicio, categoria, empresa, saldo_fila, comprobante in db.execute(consulta):
        assert saldo_fila is not None, "La consulta solo trae deudas con monto"
        grupos.setdefault(servicio.lugar_pago, []).append(
            FilaRuta(deuda, servicio, categoria, empresa, saldo_fila, comprobante)
        )
    orden = [*LUGARES_RUTA, None]
    return [GrupoRuta(lugar, grupos[lugar]) for lugar in orden if lugar in grupos]


def iniciar_ruta(
    db: Session, usuario: Usuario, deuda_ids: list[uuid.UUID], *, origen: Origen
) -> list[ResultadoDeuda]:
    """Inicia el pago de cada deuda elegida y devuelve el resultado de cada una, en el orden en que
    llegaron. No hace commit: lo hace la ruta."""
    if not deuda_ids:
        raise ErrorApi(422, "VALIDACION", "Elige al menos una deuda.", "deudas")
    if len(deuda_ids) > MAXIMO_LOTE:
        raise ErrorApi(
            422, "VALIDACION", f"Elige como máximo {MAXIMO_LOTE} deudas a la vez.", "deudas"
        )
    if len(set(deuda_ids)) != len(deuda_ids):
        raise ErrorApi(422, "VALIDACION", "Una deuda está repetida en la ruta.", "deudas")
    resultados: dict[uuid.UUID, ResultadoDeuda] = {}
    for deuda_id in sorted(deuda_ids):
        try:
            with db.begin_nested():
                inicio = iniciar_pago(db, usuario, deuda_id, origen=origen)
        except ErrorApi as error:
            resultados[deuda_id] = ResultadoDeuda(
                deuda_id, ResultadoLote.CONFLICTO, error.code, error.detail
            )
            continue
        resultado = (
            ResultadoLote.INICIADA
            if inicio.resultado == ResultadoInicio.INICIADO
            else ResultadoLote.REQUIERE_APROBACION
        )
        resultados[deuda_id] = ResultadoDeuda(
            deuda_id,
            resultado,
            repetido=inicio.repetido,
            saldo=inicio.saldo,
            moneda=inicio.deuda.moneda,
        )
    return [resultados[deuda_id] for deuda_id in deuda_ids]


def total_iniciado(resultados: list[ResultadoDeuda]) -> dict[str, Decimal]:
    """Lo que hay que llevar por lo que sí se inició, por moneda."""
    totales = {moneda: Decimal("0.00") for moneda in MONEDAS}
    for r in resultados:
        if r.resultado == ResultadoLote.INICIADA and r.saldo is not None and r.moneda:
            totales[r.moneda] += r.saldo
    return totales
