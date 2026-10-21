"""Detalle de una deuda: datos, comprobantes, abonos, historial y línea de tiempo (H17, TASK-53).

Reutiliza los contratos comunes: el saldo y la proyección de app/services/saldo.py, las acciones
de pago de app/services/pagos.py y las reglas de adjuntar de app/services/comprobantes.py. Lo ven
el gerente y su asistente; la deuda de otro gerente responde el mismo 404 que una inexistente.

La línea de tiempo se arma en app/services/linea_tiempo.py.

Las acciones las calcula el backend con las mismas reglas que cada operación vuelve a validar al
ejecutarse: el cliente solo muestra las que recibe (CA07). Una deuda anulada no tiene acciones
(CA08).
"""

import uuid
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.dependencias import gerente_de
from app.core.errores import ErrorApi
from app.core.tiempo import ahora_lima, hoy_de
from app.models import (
    Categoria,
    Comprobante,
    ComprobanteDeuda,
    Deuda,
    Empresa,
    HistorialMonto,
    OrdenPago,
    Prestamo,
    Servicio,
    Usuario,
)
from app.services.auditoria import nombre_de
from app.services.comprobantes import ESTADOS_CON_INTENTO, aplicado_en_curso
from app.services.edicion_deudas import ESTADOS_EN_CURSO
from app.services.linea_tiempo import Evento, linea_de_tiempo
from app.services.pagos import acciones_de_pago
from app.services.saldo import aplicado_de, aplicado_validado, proyeccion_sin_recibo, vencida

ESTADOS_ORDEN_ABIERTA = ("enviada", "vista", "aceptada")


class AccionDeuda(StrEnum):
    INICIAR_PAGO = "iniciar_pago"
    CANCELAR_INICIO = "cancelar_inicio"
    ADJUNTAR_COMPROBANTE = "adjuntar_comprobante"
    EDITAR = "editar"
    ANULAR = "anular"
    COMENTAR = "comentar"


@dataclass(frozen=True)
class ComprobanteFila:
    comprobante: Comprobante
    monto_aplicado: Decimal
    subido_por: str


@dataclass(frozen=True)
class CambioFila:
    cambio: HistorialMonto
    usuario: str | None


@dataclass(frozen=True)
class DetalleDeuda:
    deuda: Deuda
    servicio: Servicio
    categoria: Categoria
    empresa: str
    pagado: Decimal
    proyeccion: Decimal | None
    vencida: bool
    cuotas_total: int | None
    iniciador: Usuario | None
    orden: OrdenPago | None
    comprobantes: list[ComprobanteFila]
    historial: list[CambioFila]
    linea_tiempo: list[Evento]
    acciones: list[AccionDeuda]

    @property
    def saldo(self) -> Decimal | None:
        return None if self.deuda.monto is None else self.deuda.monto - self.pagado


def comprobantes_de(db: Session, deuda_id: uuid.UUID) -> list[ComprobanteFila]:
    filas = db.execute(
        select(Comprobante, ComprobanteDeuda.monto_aplicado, Usuario)
        .join(ComprobanteDeuda, ComprobanteDeuda.comprobante_id == Comprobante.id)
        .join(Usuario, Usuario.id == Comprobante.subido_por)
        .where(ComprobanteDeuda.deuda_id == deuda_id)
        .order_by(Comprobante.creado_en.desc(), Comprobante.id.desc())
    )
    return [ComprobanteFila(c, aplicado, nombre_de(u)) for c, aplicado, u in filas]


def historial_de(db: Session, deuda_id: uuid.UUID) -> list[CambioFila]:
    filas = db.execute(
        select(HistorialMonto, Usuario)
        .outerjoin(Usuario, Usuario.id == HistorialMonto.usuario_id)
        .where(HistorialMonto.deuda_id == deuda_id)
        .order_by(HistorialMonto.creado_en.desc(), HistorialMonto.id.desc())
    )
    return [CambioFila(cambio, nombre_de(u) if u else None) for cambio, u in filas]


def acciones_de(
    db: Session, deuda: Deuda, usuario: Usuario, orden_abierta: bool
) -> list[AccionDeuda]:
    if deuda.estado == "anulada":
        return []
    acciones: list[AccionDeuda] = []
    pago = acciones_de_pago(db, deuda, usuario)
    if pago.iniciar:
        acciones.append(AccionDeuda.INICIAR_PAGO)
    if pago.cancelar_inicio:
        acciones.append(AccionDeuda.CANCELAR_INICIO)
    # Solo la asistente sube el voucher del pago que inició (TASK-109).
    puede_adjuntar = usuario.rol == "asistente" and deuda.estado in ESTADOS_CON_INTENTO
    if puede_adjuntar and deuda.monto is not None:
        disponible = deuda.monto - aplicado_de(db, deuda.id) - aplicado_en_curso(db, deuda.id)
        if disponible > 0:
            acciones.append(AccionDeuda.ADJUNTAR_COMPROBANTE)
    if deuda.estado != "pagada":
        acciones.append(AccionDeuda.EDITAR)
    abonado = aplicado_de(db, deuda.id)
    if (
        usuario.rol == "gerente"
        and deuda.estado not in ("pagada", *ESTADOS_EN_CURSO)
        and abonado == 0
        and not orden_abierta
    ):
        acciones.append(AccionDeuda.ANULAR)
    acciones.append(AccionDeuda.COMENTAR)
    return acciones


def obtener_detalle(
    db: Session, usuario: Usuario, deuda_id: uuid.UUID, ahora: datetime | None = None
) -> DetalleDeuda:
    gerente_id = gerente_de(usuario)
    hoy = hoy_de(ahora or ahora_lima())
    fila = db.execute(
        select(
            Deuda,
            Servicio,
            Categoria,
            func.coalesce(Empresa.nombre, Servicio.empresa_nombre),
            aplicado_validado(Deuda.id),
            proyeccion_sin_recibo(),
            vencida(hoy),
        )
        .join(Servicio, Servicio.id == Deuda.servicio_id)
        .join(Categoria, Categoria.id == Servicio.categoria_id)
        .outerjoin(Empresa, Empresa.id == Servicio.empresa_id)
        .where(Deuda.id == deuda_id, Deuda.gerente_id == gerente_id)
    ).one_or_none()
    if fila is None:
        raise ErrorApi(404, "NO_ENCONTRADO", "No se encontró la deuda.")
    deuda, servicio, categoria, empresa, pagado, proyeccion, es_vencida = fila
    comprobantes = comprobantes_de(db, deuda.id)
    prestamo = db.get(Prestamo, deuda.prestamo_id) if deuda.prestamo_id else None
    iniciador = (
        db.get(Usuario, deuda.pago_iniciado_por)
        if deuda.estado == "en_proceso" and deuda.pago_iniciado_por
        else None
    )
    orden = db.scalar(
        select(OrdenPago).where(
            OrdenPago.deuda_id == deuda.id, OrdenPago.estado.in_(ESTADOS_ORDEN_ABIERTA)
        )
    )
    return DetalleDeuda(
        deuda=deuda,
        servicio=servicio,
        categoria=categoria,
        empresa=empresa or "",
        pagado=pagado,
        proyeccion=proyeccion,
        vencida=es_vencida,
        cuotas_total=prestamo.cuotas_total if prestamo else None,
        iniciador=iniciador,
        orden=orden,
        comprobantes=comprobantes,
        historial=historial_de(db, deuda.id),
        linea_tiempo=linea_de_tiempo(db, deuda, [f.comprobante for f in comprobantes]),
        acciones=acciones_de(db, deuda, usuario, orden is not None),
    )
