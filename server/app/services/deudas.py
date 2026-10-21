"""Registro manual de deudas (H11, TASK-38): CA01 a CA03 y CA09.

Periodo: si no se indica, es el mes del vencimiento, guardado como su primer día. Un vencimiento
del 31 de enero pertenece a enero, no a febrero.

Vencida (CA02): el vencimiento es anterior a hoy en Lima. Se informa en la respuesta y no
impide el registro; tampoco se guarda, porque vencida es un dato calculado. Una deuda que vence
hoy todavía no está vencida, igual que en la bandeja.

Duplicado (CA03): uq_deuda_periodo admite una sola deuda no anulada por servicio, periodo y
cuota. El registro manual no tiene cuota, que el índice cuenta como 0; las cuotas de préstamo
son mayores que 0 (ck_deuda_cuota_numero) y no chocan con ella. Un duplicado responde 409 con la
deuda existente, que siempre es del mismo gerente porque el servicio lo es. No hay confirmación
que permita saltar el índice. Una deuda anulada no ocupa el periodo.

Concurrencia: el servicio se bloquea hasta el commit. Dos registros del mismo servicio se turnan
y el segundo ve la deuda del primero; un registro y una baja simultáneos también se turnan, así
que no queda una deuda nueva en un servicio de baja. Una deuda que otro proceso inserta sin
bloquear el servicio (la generación de recurrentes) también hace esperar, porque su llave
foránea toma FOR KEY SHARE sobre el servicio. Si aun así el índice rechaza la inserción, se
responde el mismo 409.

Listado (H36, TASK-45): CA01 a CA05 y CA08, por gerente. Dos consultas con el mismo filtro: una
agrega por moneda la cantidad y los totales de todo el filtro (el total de la página sale de
ahí) y otra trae la página. Ninguna carga todas las deudas. Sin filtro de estado no aparecen las
anuladas; se ven solo pidiendo estado=anulada. Orden estable: la clave pedida y el id como
desempate, para no repetir ni omitir deudas entre páginas.
"""

import uuid
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import Select, UnaryExpression, and_, case, func, not_, or_, select, true
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.busqueda import contiene
from app.core.dependencias import Origen
from app.core.errores import ErrorApi
from app.core.paginacion import Paginacion
from app.core.tiempo import ahora_lima, hoy_de
from app.models import Categoria, Deuda, Empresa, Servicio, Usuario
from app.schemas.deudas import (
    CERO,
    ESTADOS_DEUDA,
    MONEDAS,
    DeudaEntrada,
    DeudaExistente,
    Moneda,
    OrdenListado,
    TotalesMoneda,
)
from app.services.auditoria import Accion, nombre_de, registrar_auditoria
from app.services.bandeja import validar_categoria
from app.services.notificaciones import TipoNotificacion, notificar
from app.services.saldo import (
    abonos_validados,
    aplicado_validado,
    proyeccion_sin_recibo,
    vencida,
)
from app.services.servicios import (
    fila_de,
    normalizar_codigo,
    servicio_activo_propio,
    servicio_propio,
)


@dataclass(frozen=True)
class Registro:
    deuda: Deuda
    vencida: bool


def primer_dia(texto: str) -> date:
    """Primer día del periodo AAAA-MM, como se guarda en deuda.periodo."""
    return date(int(texto[:4]), int(texto[5:7]), 1)


def periodo_de(texto: str | None, fecha_vencimiento: date) -> date:
    """Primer día del periodo AAAA-MM indicado o, si se omite, del mes del vencimiento."""
    if texto is None:
        return fecha_vencimiento.replace(day=1)
    return primer_dia(texto)


def texto_periodo(periodo: date) -> str:
    return periodo.strftime("%Y-%m")


def deuda_activa_del_periodo(db: Session, servicio_id: uuid.UUID, periodo: date) -> Deuda | None:
    """La deuda sin cuota que ocupa el servicio y el periodo en uq_deuda_periodo."""
    return db.scalar(
        select(Deuda).where(
            Deuda.servicio_id == servicio_id,
            Deuda.periodo == periodo,
            Deuda.cuota_numero.is_(None),
            Deuda.estado != "anulada",
        )
    )


def duplicado(existente: Deuda | None) -> ErrorApi:
    datos = None
    if existente is not None:
        referencia = DeudaExistente(
            id=existente.id,
            periodo=texto_periodo(existente.periodo),
            estado=existente.estado,
            monto=existente.monto,
            moneda=existente.moneda,
            fecha_vencimiento=existente.fecha_vencimiento,
        )
        datos = {"deuda_existente": referencia.model_dump(mode="json")}
    return ErrorApi(
        409,
        "DUPLICADO",
        "Ya existe una deuda de este servicio para ese periodo.",
        "periodo",
        datos=datos,
    )


def registrar_deuda(
    db: Session,
    usuario: Usuario,
    gerente_id: uuid.UUID,
    datos: DeudaEntrada,
    origen: Origen,
    ahora: datetime | None = None,
) -> Registro:
    """Gerente o asistente registran la deuda del mes de un servicio activo propio. Si la
    registra la asistente, se avisa al gerente. No hace commit."""
    servicio = servicio_activo_propio(
        db, datos.servicio_id, gerente_id, bloquear=True, campo="servicio_id"
    )
    periodo = periodo_de(datos.periodo, datos.fecha_vencimiento)
    existente = deuda_activa_del_periodo(db, servicio.id, periodo)
    if existente is not None:
        raise duplicado(existente)
    deuda = Deuda(
        gerente_id=gerente_id,
        servicio_id=servicio.id,
        periodo=periodo,
        monto=datos.monto,
        moneda=datos.moneda,
        fecha_vencimiento=datos.fecha_vencimiento,
        numero_recibo=datos.numero_recibo,
        fecha_emision=datos.fecha_emision,
        fecha_corte=datos.fecha_corte,
        pago_minimo=datos.pago_minimo,
        # En una tarjeta el monto registrado es el pago total del estado de cuenta (CA06).
        pago_total=datos.monto if datos.fecha_corte else None,
        estado="pendiente",
        origen="manual",
        creado_por=usuario.id,
    )
    try:
        with db.begin_nested():
            db.add(deuda)
            db.flush()
    except IntegrityError as error:
        if "uq_deuda_periodo" not in str(error.orig):
            raise
        # La otra deuda ya está confirmada: el índice esperó su commit para rechazar esta.
        raise duplicado(deuda_activa_del_periodo(db, servicio.id, periodo)) from None
    db.refresh(deuda)
    vencida = deuda.fecha_vencimiento < hoy_de(ahora or ahora_lima())
    registrar_auditoria(
        db,
        usuario,
        Accion.DEUDA_CREADA,
        "deuda",
        deuda.id,
        {
            "servicio_id": servicio.id,
            "periodo": texto_periodo(deuda.periodo),
            "monto": deuda.monto,
            "moneda": deuda.moneda,
            "fecha_vencimiento": deuda.fecha_vencimiento,
            "numero_recibo": deuda.numero_recibo,
            "vencida": vencida,
        },
        origen=origen,
    )
    if usuario.rol == "asistente":
        gerente = db.get(Usuario, gerente_id)
        if gerente is not None:
            nombre = servicio.alias or fila_de(db, servicio).nombre_empresa
            notificar(
                db,
                gerente,
                TipoNotificacion.DEUDA_CREADA,
                "Deuda registrada",
                f"{nombre_de(usuario)} registró la deuda de {nombre} por {deuda.moneda} "
                f"{deuda.monto}, con vencimiento el {deuda.fecha_vencimiento:%d/%m/%Y}.",
                deuda_id=deuda.id,
                clave_evento=f"deuda_creada:{deuda.id}",
                ahora=ahora,
            )
    return Registro(deuda, vencida)


@dataclass(frozen=True)
class FiltrosDeudas:
    """Filtros del listado. mes es el periodo (primer día del mes); estados vacío significa todos
    menos anulada."""

    q: str | None = None
    estados: tuple[str, ...] = ()
    vencida: bool | None = None
    categoria_id: uuid.UUID | None = None
    servicio_id: uuid.UUID | None = None
    moneda: Moneda | None = None
    mes: date | None = None
    vence_desde: date | None = None
    vence_hasta: date | None = None
    orden: OrdenListado = "vencimiento"


@dataclass(frozen=True)
class FilaDeuda:
    deuda: Deuda
    servicio: Servicio
    categoria: Categoria
    empresa: str
    pagado: Decimal
    proyeccion: Decimal | None
    vencida: bool

    @property
    def saldo(self) -> Decimal | None:
        """None si la deuda aún no tiene monto: un saldo desconocido nunca es cero."""
        return None if self.deuda.monto is None else self.deuda.monto - self.pagado


@dataclass(frozen=True)
class ListadoDeudas:
    filas: list[FilaDeuda]
    totales: dict[Moneda, TotalesMoneda]

    @property
    def total(self) -> int:
        return sum(t.cantidad for t in self.totales.values())


def con_filtros_listado[*T](
    consulta: Select[*T], gerente_id: uuid.UUID, filtros: FiltrosDeudas, hoy: date
) -> Select[*T]:
    """Deudas del gerente con su servicio, categoría y empresa del catálogo, filtradas. Búsqueda
    (CA02) en empresa, alias, código de suministro y número de recibo; el código también se
    compara normalizado, porque se guarda sin espacios y en mayúsculas."""
    consulta = (
        consulta.join(Servicio, Servicio.id == Deuda.servicio_id)
        .join(Categoria, Categoria.id == Servicio.categoria_id)
        .outerjoin(Empresa, Empresa.id == Servicio.empresa_id)
        .where(Deuda.gerente_id == gerente_id)
    )
    if filtros.estados:
        consulta = consulta.where(Deuda.estado.in_(filtros.estados))
    else:
        consulta = consulta.where(Deuda.estado != "anulada")
    if filtros.vencida is not None:
        es_vencida = vencida(hoy)
        consulta = consulta.where(es_vencida if filtros.vencida else not_(es_vencida))
    if filtros.categoria_id is not None:
        consulta = consulta.where(Servicio.categoria_id == filtros.categoria_id)
    if filtros.servicio_id is not None:
        consulta = consulta.where(Deuda.servicio_id == filtros.servicio_id)
    if filtros.moneda is not None:
        consulta = consulta.where(Deuda.moneda == filtros.moneda)
    if filtros.mes is not None:
        consulta = consulta.where(Deuda.periodo == filtros.mes)
    if filtros.vence_desde is not None:
        consulta = consulta.where(Deuda.fecha_vencimiento >= filtros.vence_desde)
    if filtros.vence_hasta is not None:
        consulta = consulta.where(Deuda.fecha_vencimiento <= filtros.vence_hasta)
    if filtros.q:
        condiciones = [
            contiene(columna, filtros.q)
            for columna in (
                Empresa.nombre,
                Servicio.empresa_nombre,
                Servicio.alias,
                Servicio.codigo_suministro,
                Deuda.numero_recibo,
            )
        ]
        codigo = normalizar_codigo(filtros.q)
        if codigo != filtros.q:
            condiciones.append(contiene(Servicio.codigo_suministro, codigo))
        consulta = consulta.where(or_(*condiciones))
    return consulta


def orden_listado(orden: OrdenListado) -> list[UnaryExpression[Any]]:
    """Orden pedido (CA04) con el id al final: el orden es total y estable entre páginas. Sin monto
    va al final en ambos sentidos. El estado sigue su ciclo de vida, no el orden alfabético."""
    descendente = orden.startswith("-")
    campo = orden.removeprefix("-")

    def sentido(columna: Any) -> UnaryExpression[Any]:
        return columna.desc() if descendente else columna.asc()

    claves: list[UnaryExpression[Any]] = []
    if campo == "monto":
        claves = [sentido(Deuda.monto).nulls_last(), Deuda.fecha_vencimiento.asc()]
    elif campo == "estado":
        posicion = case({e: i for i, e in enumerate(ESTADOS_DEUDA)}, value=Deuda.estado)
        claves = [sentido(posicion), Deuda.fecha_vencimiento.asc()]
    else:
        claves = [sentido(Deuda.fecha_vencimiento)]
    return [*claves, sentido(Deuda.id)]


def totales_por_moneda(
    db: Session, gerente_id: uuid.UUID, filtros: FiltrosDeudas, hoy: date
) -> dict[Moneda, TotalesMoneda]:
    """Cantidad y totales de todo el filtro por moneda, en una sola consulta (CA08). Siempre trae
    PEN y USD, en cero si no hay deudas de esa moneda."""
    abonos = abonos_validados()
    proyeccion = proyeccion_sin_recibo()
    sin_monto = Deuda.monto.is_(None)
    consulta = select(
        Deuda.moneda,
        func.count().label("cantidad"),
        func.coalesce(func.sum(Deuda.monto), CERO).label("monto"),
        func.coalesce(func.sum(abonos.c.aplicado), CERO).label("pagado"),
        func.coalesce(func.sum(Deuda.monto - abonos.c.aplicado), CERO).label("saldo"),
        func.count().filter(sin_monto).label("sin_monto"),
        func.coalesce(func.sum(proyeccion), CERO).label("proyectado"),
        func.count().filter(and_(sin_monto, proyeccion.is_(None))).label("sin_estimacion"),
    ).select_from(Deuda)
    consulta = con_filtros_listado(
        consulta.join(abonos, true()), gerente_id, filtros, hoy
    ).group_by(Deuda.moneda)
    totales = {moneda: TotalesMoneda() for moneda in MONEDAS}
    for fila in db.execute(consulta).mappings():
        totales[fila["moneda"]] = TotalesMoneda.model_validate(dict(fila))
    return totales


def listar_deudas(
    db: Session,
    gerente_id: uuid.UUID,
    filtros: FiltrosDeudas,
    parametros: Paginacion,
    ahora: datetime | None = None,
) -> ListadoDeudas:
    """Página del listado y totales del filtro. Una categoría o un servicio ajeno o inexistente
    responde 404: una lista vacía diría que no hay deudas."""
    if filtros.categoria_id is not None:
        validar_categoria(db, filtros.categoria_id, gerente_id)
    if filtros.servicio_id is not None:
        servicio_propio(db, filtros.servicio_id, gerente_id, campo="servicio")
    hoy = hoy_de(ahora or ahora_lima())
    totales = totales_por_moneda(db, gerente_id, filtros, hoy)
    consulta = select(
        Deuda,
        Servicio,
        Categoria,
        func.coalesce(Empresa.nombre, Servicio.empresa_nombre),
        aplicado_validado(Deuda.id),
        proyeccion_sin_recibo(),
        vencida(hoy),
    ).select_from(Deuda)
    consulta = (
        con_filtros_listado(consulta, gerente_id, filtros, hoy)
        .order_by(*orden_listado(filtros.orden))
        .offset(parametros.offset)
        .limit(parametros.size)
    )
    filas = [
        FilaDeuda(
            deuda=deuda,
            servicio=servicio,
            categoria=categoria,
            empresa=empresa,
            pagado=pagado,
            proyeccion=proyeccion,
            vencida=es_vencida,
        )
        for deuda, servicio, categoria, empresa, pagado, proyeccion, es_vencida in db.execute(
            consulta
        )
    ]
    return ListadoDeudas(filas=filas, totales=totales)
