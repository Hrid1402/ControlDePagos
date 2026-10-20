"""Servicio de gestión de categorías de servicios (H09, TASK-28).

Implementa la creación por gerente o asistente (CA04), la edición y eliminación exclusivas
del gerente (CA04), y la regla de mover servicios antes de eliminar una categoría (CA05).

El tipo de la categoría define qué campos pide la deuda (CA03): mientras sus servicios tengan
deudas o recurrencias, no se cambia su tipo ni se mueven a una categoría de otro tipo. Las
precargadas no se eliminan (CA01).
"""

import uuid

from sqlalchemy import exists, func, or_, select
from sqlalchemy.orm import Session

from app.core.dependencias import Origen
from app.core.errores import ErrorApi
from app.models import Categoria, Deuda, Recurrencia, Servicio, Usuario
from app.schemas.categorias import (
    ActualizarCategoriaEntrada,
    CategoriaSalida,
    CrearCategoriaEntrada,
    MensajeEliminacionCategoria,
)
from app.services.auditoria import Accion, diferencias, registrar_auditoria


def deudas_por_categoria(db: Session, gerente_id: uuid.UUID) -> dict[uuid.UUID, int]:
    """Deudas vigentes (no anuladas) de cada categoría, a través de sus servicios (CA06)."""
    filas = db.execute(
        select(Servicio.categoria_id, func.count(Deuda.id))
        .join(Deuda, Deuda.servicio_id == Servicio.id)
        .where(Servicio.gerente_id == gerente_id, Deuda.estado != "anulada")
        .group_by(Servicio.categoria_id)
    ).all()
    return {categoria_id: cantidad for categoria_id, cantidad in filas}


def tipo_en_uso(db: Session, categoria_id: uuid.UUID) -> bool:
    """Si algún servicio de la categoría tiene deudas o recurrencias, que dependen de su tipo."""
    servicios = select(Servicio.id).where(Servicio.categoria_id == categoria_id)
    return bool(
        db.scalar(
            select(
                or_(
                    exists().where(Deuda.servicio_id.in_(servicios)),
                    exists().where(Recurrencia.servicio_id.in_(servicios)),
                )
            )
        )
    )


def listar_categorias(db: Session, gerente_id: uuid.UUID) -> list[CategoriaSalida]:
    """Lista las categorías del gerente con el conteo de servicios activos asociados."""
    subquery = (
        select(
            Servicio.categoria_id,
            func.count(Servicio.id).label("conteo"),
        )
        .where(
            Servicio.gerente_id == gerente_id,
            Servicio.eliminado_en.is_(None),
        )
        .group_by(Servicio.categoria_id)
        .subquery()
    )

    filas = db.execute(
        select(
            Categoria,
            func.coalesce(subquery.c.conteo, 0).label("cantidad_servicios"),
        )
        .outerjoin(subquery, Categoria.id == subquery.c.categoria_id)
        .where(Categoria.gerente_id == gerente_id)
        .order_by(Categoria.precargada.desc(), Categoria.nombre.asc())
    ).all()

    deudas = deudas_por_categoria(db, gerente_id)
    resultado: list[CategoriaSalida] = []
    for categoria, cantidad in filas:
        salida = CategoriaSalida.model_validate(categoria)
        salida.cantidad_servicios = cantidad
        salida.cantidad_deudas = deudas.get(categoria.id, 0)
        resultado.append(salida)
    return resultado


def obtener_categoria(
    db: Session, gerente_id: uuid.UUID, categoria_id: uuid.UUID
) -> CategoriaSalida:
    """Devuelve el detalle de una categoría con su conteo de servicios."""
    categoria = db.get(Categoria, categoria_id)
    if categoria is None or categoria.gerente_id != gerente_id:
        raise ErrorApi(404, "NO_ENCONTRADO", "No se encontró la categoría solicitada.")

    cantidad = (
        db.scalar(
            select(func.count(Servicio.id)).where(
                Servicio.categoria_id == categoria_id,
                Servicio.gerente_id == gerente_id,
                Servicio.eliminado_en.is_(None),
            )
        )
        or 0
    )
    salida = CategoriaSalida.model_validate(categoria)
    salida.cantidad_servicios = cantidad
    salida.cantidad_deudas = deudas_por_categoria(db, gerente_id).get(categoria.id, 0)
    return salida


def crear_categoria(
    db: Session,
    usuario: Usuario,
    gerente_id: uuid.UUID,
    datos: CrearCategoriaEntrada,
    origen: Origen,
) -> CategoriaSalida:
    """Crea una categoría para el gerente (CA04: gerente o asistente)."""
    nombre_limpio = datos.nombre.strip()
    existente = db.scalar(
        select(Categoria.id).where(
            Categoria.gerente_id == gerente_id,
            func.lower(Categoria.nombre) == nombre_limpio.lower(),
        )
    )
    if existente is not None:
        raise ErrorApi(
            409,
            "CATEGORIA_DUPLICADA",
            f"Ya existe una categoría con el nombre '{nombre_limpio}'.",
            "nombre",
        )

    categoria = Categoria(
        gerente_id=gerente_id,
        nombre=nombre_limpio,
        color=datos.color,
        icono=datos.icono,
        tipo=datos.tipo,
        precargada=False,
        creado_por=usuario.id,
    )
    db.add(categoria)
    db.flush()

    registrar_auditoria(
        db,
        usuario,
        Accion.CATEGORIA_CREADA,
        "categoria",
        categoria.id,
        {
            "nombre": categoria.nombre,
            "color": categoria.color,
            "icono": categoria.icono,
            "tipo": categoria.tipo,
        },
        origen=origen,
    )

    db.commit()
    db.refresh(categoria)
    salida = CategoriaSalida.model_validate(categoria)
    salida.cantidad_servicios = 0
    return salida


def actualizar_categoria(
    db: Session,
    usuario: Usuario,
    gerente_id: uuid.UUID,
    categoria_id: uuid.UUID,
    datos: ActualizarCategoriaEntrada,
    origen: Origen,
) -> CategoriaSalida:
    """Edita una categoría existente (CA04: exclusivo del gerente)."""
    categoria = db.get(Categoria, categoria_id)
    if categoria is None or categoria.gerente_id != gerente_id:
        raise ErrorApi(404, "NO_ENCONTRADO", "No se encontró la categoría solicitada.")

    nombre_limpio = datos.nombre.strip()
    if nombre_limpio.lower() != categoria.nombre.lower():
        existente = db.scalar(
            select(Categoria.id).where(
                Categoria.gerente_id == gerente_id,
                func.lower(Categoria.nombre) == nombre_limpio.lower(),
                Categoria.id != categoria.id,
            )
        )
        if existente is not None:
            raise ErrorApi(
                409,
                "CATEGORIA_DUPLICADA",
                f"Ya existe una categoría con el nombre '{nombre_limpio}'.",
                "nombre",
            )

    if datos.tipo is not None and datos.tipo != categoria.tipo and tipo_en_uso(db, categoria.id):
        raise ErrorApi(
            409,
            "TIPO_EN_USO",
            "No puedes cambiar el tipo: sus servicios ya tienen deudas o recurrencias que "
            "dependen de él. Crea otra categoría con el tipo nuevo.",
            "tipo",
        )

    antes = {
        "nombre": categoria.nombre,
        "color": categoria.color,
        "icono": categoria.icono,
        "tipo": categoria.tipo,
    }

    categoria.nombre = nombre_limpio
    if datos.color is not None:
        categoria.color = datos.color
    if datos.icono is not None:
        categoria.icono = datos.icono
    if datos.tipo is not None:
        categoria.tipo = datos.tipo

    despues = {
        "nombre": categoria.nombre,
        "color": categoria.color,
        "icono": categoria.icono,
        "tipo": categoria.tipo,
    }

    cambios = diferencias(antes, despues)
    if cambios:
        registrar_auditoria(
            db,
            usuario,
            Accion.CATEGORIA_ACTUALIZADA,
            "categoria",
            categoria.id,
            cambios,
            origen=origen,
        )

    db.commit()
    db.refresh(categoria)
    return obtener_categoria(db, gerente_id, categoria.id)


def mover_servicios(
    db: Session,
    usuario: Usuario,
    gerente_id: uuid.UUID,
    origen_id: uuid.UUID,
    destino_id: uuid.UUID,
    origen: Origen,
    campo: str = "destino_id",
) -> int:
    """Mueve todos los servicios de una categoría a otra (CA05). A una de otro tipo solo si
    ninguno tiene deudas ni recurrencias: sus campos dependen del tipo."""
    if origen_id == destino_id:
        raise ErrorApi(
            400,
            "MISMA_CATEGORIA",
            "La categoría de destino no puede ser la misma que la de origen.",
            campo,
        )

    cat_origen = db.get(Categoria, origen_id)
    if cat_origen is None or cat_origen.gerente_id != gerente_id:
        raise ErrorApi(404, "NO_ENCONTRADO", "No se encontró la categoría de origen.")

    cat_destino = db.get(Categoria, destino_id)
    if cat_destino is None or cat_destino.gerente_id != gerente_id:
        raise ErrorApi(404, "NO_ENCONTRADO", "No se encontró la categoría de destino.")

    if cat_destino.tipo != cat_origen.tipo and tipo_en_uso(db, origen_id):
        raise ErrorApi(
            409,
            "TIPO_INCOMPATIBLE",
            "Sus servicios tienen deudas o recurrencias: muévelos a una categoría del mismo tipo.",
            campo,
        )

    # Mover tanto activos como eliminados para no dejar llaves foráneas bloqueadas
    servicios = db.scalars(
        select(Servicio).where(
            Servicio.categoria_id == origen_id,
            Servicio.gerente_id == gerente_id,
        )
    ).all()

    total = len(servicios)
    for s in servicios:
        s.categoria_id = destino_id

    if total > 0:
        registrar_auditoria(
            db,
            usuario,
            Accion.CATEGORIA_ACTUALIZADA,
            "categoria",
            origen_id,
            {
                "accion": "servicios_movidos",
                "origen_id": str(origen_id),
                "destino_id": str(destino_id),
                "cantidad": total,
            },
            origen=origen,
        )

    db.commit()
    return total


def eliminar_categoria(
    db: Session,
    usuario: Usuario,
    gerente_id: uuid.UUID,
    categoria_id: uuid.UUID,
    mover_a: uuid.UUID | None,
    origen: Origen,
) -> MensajeEliminacionCategoria:
    """Elimina una categoría, traspasando primero sus servicios si se especificó destino (CA05)."""
    categoria = db.get(Categoria, categoria_id)
    if categoria is None or categoria.gerente_id != gerente_id:
        raise ErrorApi(404, "NO_ENCONTRADO", "No se encontró la categoría solicitada.")
    if categoria.precargada:
        raise ErrorApi(
            409, "CATEGORIA_PRECARGADA", "Las categorías precargadas no se pueden eliminar."
        )

    conteo_servicios = (
        db.scalar(
            select(func.count(Servicio.id)).where(
                Servicio.categoria_id == categoria_id,
                Servicio.gerente_id == gerente_id,
            )
        )
        or 0
    )

    servicios_movidos = 0
    if conteo_servicios > 0:
        if mover_a is None:
            raise ErrorApi(
                409,
                "CATEGORIA_CON_SERVICIOS",
                "La categoría tiene servicios asociados; "
                "muévelos a otra categoría antes de eliminarla.",
                "mover_a",
            )
        servicios_movidos = mover_servicios(
            db, usuario, gerente_id, categoria_id, mover_a, origen, campo="mover_a"
        )

    nombre_categoria = categoria.nombre
    tipo_categoria = categoria.tipo

    db.delete(categoria)
    registrar_auditoria(
        db,
        usuario,
        Accion.CATEGORIA_ELIMINADA,
        "categoria",
        categoria_id,
        {
            "nombre": nombre_categoria,
            "tipo": tipo_categoria,
            "servicios_movidos": servicios_movidos,
        },
        origen=origen,
    )
    db.commit()

    return MensajeEliminacionCategoria(
        mensaje=f"Categoría '{nombre_categoria}' eliminada exitosamente.",
        servicios_movidos=servicios_movidos,
    )
