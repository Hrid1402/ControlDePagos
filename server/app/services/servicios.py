"""Servicios del gerente (H10, TASK-33): registro, edición, baja, reactivación y listado.

Unicidad (CA03): uq_servicio_codigo compara gerente, coalesce(empresa_id, lower(empresa_nombre))
y el código exacto. Por eso el código se guarda ya normalizado (sin espacios y en mayúsculas) y
un nombre manual que coincide con una empresa del catálogo se guarda como su empresa_id: así
"calidda" escrito a mano y Cálidda elegida de la lista son el mismo servicio.

La baja no es una eliminación: solo cambia estado a 'baja' y desactiva la recurrencia;
eliminado_en no se toca, el código sigue ocupado y las deudas pendientes se conservan (CA08).
"""

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from sqlalchemy import Select, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.dependencias import Origen
from app.core.errores import ErrorApi
from app.models import Categoria, Deuda, Empresa, Recurrencia, Servicio, Usuario
from app.schemas.servicios import FiltroEstado, ServicioEntrada
from app.services.auditoria import Accion, diferencias, registrar_auditoria
from app.services.empresas import cumple_patron, empresa_del_catalogo

# Deudas que ya no se cobran: no cuentan para la advertencia de cambio de código.
ESTADOS_CERRADOS = ("pagada", "anulada")

CAMPOS_AUDITADOS = (
    "categoria_id",
    "empresa_id",
    "empresa_nombre",
    "codigo_suministro",
    "titular",
    "alias",
    "lugar_pago",
    "notas",
)


@dataclass(frozen=True)
class FilaServicio:
    servicio: Servicio
    categoria: Categoria
    empresa: Empresa | None

    @property
    def nombre_empresa(self) -> str:
        if self.empresa is not None:
            return self.empresa.nombre
        return self.servicio.empresa_nombre or ""


def normalizar_codigo(codigo: str) -> str:
    """Sin espacios y en mayúsculas: " 12 34-a " y "1234-A" son el mismo código."""
    return "".join(codigo.split()).upper()


def normalizar_nombre(nombre: str) -> str:
    """Sin espacios repetidos ni en los extremos; se conservan mayúsculas y acentos."""
    return " ".join(nombre.split())


def no_encontrado(campo: str | None = None) -> ErrorApi:
    return ErrorApi(404, "NO_ENCONTRADO", "No se encontró el recurso solicitado.", campo)


def duplicado() -> ErrorApi:
    return ErrorApi(
        409,
        "DUPLICADO",
        "Ya tienes registrado un servicio de esta empresa con ese código de suministro.",
        "codigo_suministro",
    )


def categoria_propia(db: Session, categoria_id: uuid.UUID, gerente_id: uuid.UUID) -> Categoria:
    """La asistente puede usar cualquier categoría de su gerente, de cualquier tipo (CA09)."""
    categoria = db.get(Categoria, categoria_id)
    if categoria is None or categoria.gerente_id != gerente_id:
        raise no_encontrado("categoria_id")
    return categoria


def servicio_propio(
    db: Session, servicio_id: uuid.UUID, gerente_id: uuid.UUID, bloquear: bool = False
) -> Servicio:
    """Servicio del gerente, de baja o no. Uno ajeno o eliminado responde el mismo 404."""
    consulta = select(Servicio).where(
        Servicio.id == servicio_id,
        Servicio.gerente_id == gerente_id,
        Servicio.eliminado_en.is_(None),
    )
    if bloquear:
        consulta = consulta.with_for_update().execution_options(populate_existing=True)
    servicio = db.scalar(consulta)
    if servicio is None:
        raise no_encontrado()
    return servicio


def servicio_activo_propio(
    db: Session, servicio_id: uuid.UUID, gerente_id: uuid.UUID, bloquear: bool = False
) -> Servicio:
    """Servicio que admite cambios y deudas nuevas: uno dado de baja responde 409."""
    servicio = servicio_propio(db, servicio_id, gerente_id, bloquear)
    if servicio.estado == "baja":
        raise ErrorApi(409, "SERVICIO_DE_BAJA", "El servicio está dado de baja.")
    return servicio


def resolver_empresa(db: Session, datos: ServicioEntrada) -> tuple[Empresa | None, str | None]:
    """Empresa del catálogo o nombre manual (CA01). Devuelve (empresa, empresa_nombre)."""
    if (datos.empresa_id is None) == (datos.empresa_nombre is None):
        raise ErrorApi(
            422,
            "VALIDACION",
            "Elige una empresa de la lista o escribe su nombre en «Otra empresa».",
            "empresa",
        )
    if datos.empresa_id is not None:
        empresa = db.get(Empresa, datos.empresa_id)
        if empresa is None:
            raise no_encontrado("empresa_id")
        return empresa, None
    nombre = normalizar_nombre(datos.empresa_nombre or "")
    conocida = empresa_del_catalogo(db, nombre)
    if conocida is not None:
        return conocida, None
    return None, nombre


def validar_codigo(codigo: str, empresa: Empresa | None) -> str:
    """Código obligatorio y, si la empresa tiene patrón, con su formato (CA02)."""
    normal = normalizar_codigo(codigo)
    if not normal:
        raise ErrorApi(
            422, "VALIDACION", "El código de suministro es obligatorio.", "codigo_suministro"
        )
    if empresa is not None and not cumple_patron(empresa, normal):
        raise ErrorApi(
            422,
            "VALIDACION",
            f"El código de suministro no tiene el formato de {empresa.nombre}.",
            "codigo_suministro",
        )
    return normal


def existe_duplicado(
    db: Session,
    gerente_id: uuid.UUID,
    empresa: Empresa | None,
    empresa_nombre: str | None,
    codigo: str,
    excluir_id: uuid.UUID | None = None,
) -> bool:
    """Misma comparación que uq_servicio_codigo, incluidos los servicios dados de baja."""
    if empresa is not None:
        misma_empresa = Servicio.empresa_id == empresa.id
    else:
        misma_empresa = Servicio.empresa_id.is_(None) & (
            func.lower(Servicio.empresa_nombre) == func.lower(empresa_nombre)
        )
    consulta = select(Servicio.id).where(
        Servicio.gerente_id == gerente_id,
        Servicio.eliminado_en.is_(None),
        Servicio.codigo_suministro == codigo,
        misma_empresa,
    )
    if excluir_id is not None:
        consulta = consulta.where(Servicio.id != excluir_id)
    return db.scalar(consulta.limit(1)) is not None


def guardar(db: Session, servicio: Servicio) -> None:
    """Envía el cambio a la base. Si otro registro tomó la misma empresa y código entre la
    consulta y el guardado, el índice lo rechaza y se responde el mismo 409."""
    try:
        with db.begin_nested():
            db.add(servicio)
            db.flush()
    except IntegrityError as error:
        if "uq_servicio_codigo" not in str(error.orig):
            raise
        if servicio.id is not None:
            # En una edición, descarta los valores que no se guardaron.
            db.expire(servicio)
        raise duplicado() from None


def datos_auditables(servicio: Servicio) -> dict[str, Any]:
    return {campo: getattr(servicio, campo) for campo in CAMPOS_AUDITADOS}


def aplicar(
    db: Session, servicio: Servicio, gerente_id: uuid.UUID, datos: ServicioEntrada
) -> tuple[Categoria, Empresa | None]:
    """Valida los datos y los copia al servicio, sin guardarlo."""
    categoria = categoria_propia(db, datos.categoria_id, gerente_id)
    empresa, empresa_nombre = resolver_empresa(db, datos)
    codigo = validar_codigo(datos.codigo_suministro, empresa)
    if existe_duplicado(db, gerente_id, empresa, empresa_nombre, codigo, servicio.id):
        raise duplicado()
    servicio.categoria_id = categoria.id
    servicio.empresa_id = empresa.id if empresa is not None else None
    servicio.empresa_nombre = empresa_nombre
    servicio.codigo_suministro = codigo
    servicio.titular = datos.titular
    servicio.alias = datos.alias
    servicio.lugar_pago = datos.lugar_pago
    servicio.notas = datos.notas
    return categoria, empresa


def crear_servicio(
    db: Session, usuario: Usuario, gerente_id: uuid.UUID, datos: ServicioEntrada, origen: Origen
) -> FilaServicio:
    """Gerente o asistente registran el servicio una sola vez (CA01 a CA06 y CA09). No hace
    commit."""
    servicio = Servicio(gerente_id=gerente_id, creado_por=usuario.id)
    categoria, empresa = aplicar(db, servicio, gerente_id, datos)
    guardar(db, servicio)
    db.refresh(servicio)
    registrar_auditoria(
        db,
        usuario,
        Accion.SERVICIO_CREADO,
        "servicio",
        servicio.id,
        datos_auditables(servicio),
        origen=origen,
    )
    return FilaServicio(servicio, categoria, empresa)


def contar_deudas_pendientes(db: Session, servicio_id: uuid.UUID) -> int:
    return (
        db.scalar(
            select(func.count())
            .select_from(Deuda)
            .where(Deuda.servicio_id == servicio_id, Deuda.estado.not_in(ESTADOS_CERRADOS))
        )
        or 0
    )


@dataclass(frozen=True)
class Edicion:
    fila: FilaServicio
    codigo_cambiado: bool
    deudas_pendientes: int


def editar_servicio(
    db: Session,
    usuario: Usuario,
    gerente_id: uuid.UUID,
    servicio_id: uuid.UUID,
    datos: ServicioEntrada,
    origen: Origen,
) -> Edicion:
    """Reemplaza los datos del servicio. Si cambia el código, informa cuántas deudas pendientes
    tiene para la advertencia (CA07); no las modifica. No hace commit."""
    servicio = servicio_activo_propio(db, servicio_id, gerente_id, bloquear=True)
    anterior = datos_auditables(servicio)
    categoria, empresa = aplicar(db, servicio, gerente_id, datos)
    guardar(db, servicio)
    db.refresh(servicio)
    nuevo = datos_auditables(servicio)
    codigo_cambiado = anterior["codigo_suministro"] != nuevo["codigo_suministro"]
    pendientes = contar_deudas_pendientes(db, servicio.id)
    detalle = diferencias(anterior, nuevo)
    if detalle:
        if codigo_cambiado:
            detalle["deudas_pendientes"] = pendientes
        registrar_auditoria(
            db,
            usuario,
            Accion.SERVICIO_ACTUALIZADO,
            "servicio",
            servicio.id,
            detalle,
            origen=origen,
        )
    return Edicion(FilaServicio(servicio, categoria, empresa), codigo_cambiado, pendientes)


@dataclass(frozen=True)
class Baja:
    fila: FilaServicio
    recurrencias_desactivadas: int
    deudas_pendientes: int


def dar_de_baja(db: Session, gerente: Usuario, servicio_id: uuid.UUID, origen: Origen) -> Baja:
    """Detiene las deudas nuevas y conserva las pendientes (CA08): desactiva la recurrencia y
    no toca deudas, órdenes ni pagos en curso. No hace commit."""
    servicio = servicio_activo_propio(db, servicio_id, gerente.id, bloquear=True)
    servicio.estado = "baja"
    desactivadas = len(
        db.execute(
            update(Recurrencia)
            .where(Recurrencia.servicio_id == servicio.id, Recurrencia.activa.is_(True))
            .values(activa=False)
            .returning(Recurrencia.id)
        ).all()
    )
    db.flush()
    db.refresh(servicio)
    pendientes = contar_deudas_pendientes(db, servicio.id)
    registrar_auditoria(
        db,
        gerente,
        Accion.SERVICIO_DADO_DE_BAJA,
        "servicio",
        servicio.id,
        {"recurrencias_desactivadas": desactivadas, "deudas_pendientes": pendientes},
        origen=origen,
    )
    return Baja(fila_de(db, servicio), desactivadas, pendientes)


def reactivar_servicio(
    db: Session, gerente: Usuario, servicio_id: uuid.UUID, origen: Origen
) -> FilaServicio:
    """Vuelve a activar el servicio. Sus recurrencias siguen inactivas: se reactivan aparte para
    no generar deudas de meses en que el servicio estuvo de baja. No hace commit."""
    servicio = servicio_propio(db, servicio_id, gerente.id, bloquear=True)
    if servicio.estado != "baja":
        raise ErrorApi(409, "CONFLICTO", "El servicio ya está activo.")
    servicio.estado = "activo"
    db.flush()
    db.refresh(servicio)
    registrar_auditoria(
        db, gerente, Accion.SERVICIO_REACTIVADO, "servicio", servicio.id, {}, origen=origen
    )
    return fila_de(db, servicio)


@dataclass(frozen=True)
class FiltrosServicios:
    q: str | None = None
    categoria_id: uuid.UUID | None = None
    estado: FiltroEstado = "activo"


def consulta_servicios(
    db: Session, gerente_id: uuid.UUID, filtros: FiltrosServicios
) -> Select[Servicio]:
    """Servicios del gerente por nombre visible (alias o empresa). Búsqueda en alias, titular,
    código y empresa; filtro por categoría (CA10) y por estado."""
    nombre = func.coalesce(Servicio.alias, Empresa.nombre, Servicio.empresa_nombre)
    consulta = (
        select(Servicio)
        .outerjoin(Empresa, Empresa.id == Servicio.empresa_id)
        .where(Servicio.gerente_id == gerente_id, Servicio.eliminado_en.is_(None))
        .order_by(func.lower(nombre))
    )
    if filtros.categoria_id is not None:
        categoria_propia(db, filtros.categoria_id, gerente_id)
        consulta = consulta.where(Servicio.categoria_id == filtros.categoria_id)
    if filtros.estado != "todos":
        consulta = consulta.where(Servicio.estado == filtros.estado)
    if filtros.q:
        patron = filtros.q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        buscado = f"%{patron}%"
        consulta = consulta.where(
            or_(
                *(
                    columna.ilike(buscado, escape="\\")
                    for columna in (
                        Servicio.alias,
                        Servicio.titular,
                        Servicio.codigo_suministro,
                        Empresa.nombre,
                        Servicio.empresa_nombre,
                    )
                )
            )
        )
    return consulta


def filas_de(db: Session, servicios: Sequence[Servicio]) -> list[FilaServicio]:
    """Completa categoría y empresa de varios servicios con dos consultas."""
    categorias = {
        c.id: c
        for c in db.scalars(
            select(Categoria).where(Categoria.id.in_({s.categoria_id for s in servicios}))
        )
    }
    ids_empresa = {s.empresa_id for s in servicios if s.empresa_id is not None}
    empresas = (
        {e.id: e for e in db.scalars(select(Empresa).where(Empresa.id.in_(ids_empresa)))}
        if ids_empresa
        else {}
    )
    return [
        FilaServicio(
            s,
            categorias[s.categoria_id],
            empresas.get(s.empresa_id) if s.empresa_id is not None else None,
        )
        for s in servicios
    ]


def fila_de(db: Session, servicio: Servicio) -> FilaServicio:
    [fila] = filas_de(db, [servicio])
    return fila
