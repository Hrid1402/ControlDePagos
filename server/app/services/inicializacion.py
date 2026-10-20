"""Inicialización idempotente de un gerente y de sus categorías precargadas (TASK-27, H09).

No existe registro público de gerentes (H01): se crean con el comando administrativo
app.comandos.inicializar_gerente, que llama a este servicio. Repetirlo no duplica nada:

- Si el username no existe, crea el gerente activo con su contraseña inicial y sus categorías.
- Si existe un gerente activo con ese username (sin distinguir mayúsculas), no cambia su
  contraseña ni sus datos; solo agrega las categorías precargadas que le falten.
- Si el username es de una asistente, de un gerente inactivo o de una cuenta eliminada, es un
  conflicto y no se cambia nada.

Dos ejecuciones simultáneas no se pisan: la cuenta y las categorías se insertan con ON CONFLICT
DO NOTHING sobre uq_usuario_username y uq_categoria_nombre. La segunda espera a que la primera
confirme y encuentra lo que esta creó.
"""

import uuid
from dataclasses import dataclass, field

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.dependencias import Origen
from app.core.seguridad import hashear_contrasena
from app.models import Categoria, HistorialContrasena, Usuario
from app.schemas.inicializacion import DatosGerente
from app.services.auditoria import Accion, registrar_auditoria


@dataclass(frozen=True)
class CategoriaPrecargada:
    nombre: str
    tipo: str
    color: str
    icono: str


# H09 CA01. Los íconos son de PrimeIcons, como el valor por defecto de la tabla (pi-tag).
CATEGORIAS_PRECARGADAS = (
    CategoriaPrecargada("Luz", "servicio_variable", "#F59E0B", "pi-bolt"),
    CategoriaPrecargada("Agua", "servicio_variable", "#0EA5E9", "pi-eye-dropper"),
    CategoriaPrecargada("Gas", "servicio_variable", "#F97316", "pi-gauge"),
    CategoriaPrecargada("Telefonía e internet", "monto_fijo", "#8B5CF6", "pi-wifi"),
    CategoriaPrecargada("Tarjeta de crédito", "tarjeta", "#EF4444", "pi-credit-card"),
    CategoriaPrecargada("Préstamo", "prestamo", "#10B981", "pi-building-columns"),
    CategoriaPrecargada("Otros", "servicio_variable", "#64748B", "pi-tag"),
)


class ConflictoInicializacion(Exception):
    """El username o el correo pertenecen a una cuenta que el comando no puede usar."""


@dataclass
class CategoriasPrecargadas:
    creadas: list[str] = field(default_factory=list)
    existentes: list[str] = field(default_factory=list)
    # Ya había una categoría propia del gerente con ese nombre: se deja como está.
    manuales: list[str] = field(default_factory=list)


@dataclass
class Inicializacion:
    gerente: Usuario
    creado: bool
    categorias: CategoriasPrecargadas
    # Datos indicados que difieren de los registrados y no se aplicaron.
    datos_distintos: list[str] = field(default_factory=list)


def buscar_cuenta(db: Session, username: str, bloquear: bool = False) -> Usuario | None:
    """Cuenta del username sin distinguir mayúsculas, eliminada o no: uq_usuario_username no es
    parcial, así que su username sigue ocupado."""
    consulta = select(Usuario).where(func.lower(Usuario.username) == username.lower())
    if bloquear:
        consulta = consulta.with_for_update().execution_options(populate_existing=True)
    return db.scalar(consulta)


def validar_existente(usuario: Usuario) -> None:
    if usuario.rol != "gerente":
        raise ConflictoInicializacion("El usuario indicado pertenece a una cuenta de asistente.")
    if usuario.eliminado_en is not None:
        raise ConflictoInicializacion(
            "El usuario indicado pertenece a una cuenta eliminada y no se puede reutilizar."
        )
    if usuario.estado != "activa":
        raise ConflictoInicializacion(
            "El gerente indicado está inactivo; el comando no lo reactiva."
        )


def correo_en_uso() -> ConflictoInicializacion:
    return ConflictoInicializacion("El correo indicado ya lo usa otra cuenta.")


def precargar_categorias(db: Session, gerente: Usuario, origen: Origen) -> CategoriasPrecargadas:
    """Crea las categorías precargadas que le falten al gerente. Es el único punto de entrada:
    cualquier vía que cree un gerente debe llamarla. No hace commit."""
    insertadas = db.execute(
        insert(Categoria)
        .values(
            [
                {
                    "gerente_id": gerente.id,
                    "nombre": c.nombre,
                    "tipo": c.tipo,
                    "color": c.color,
                    "icono": c.icono,
                    "precargada": True,
                }
                for c in CATEGORIAS_PRECARGADAS
            ]
        )
        .on_conflict_do_nothing(index_elements=[Categoria.gerente_id, func.lower(Categoria.nombre)])
        .returning(Categoria.id, Categoria.nombre)
    ).all()
    creadas: dict[str, uuid.UUID] = {nombre: id_ for id_, nombre in insertadas}

    resultado = CategoriasPrecargadas()
    for precargada in CATEGORIAS_PRECARGADAS:
        if precargada.nombre in creadas:
            resultado.creadas.append(precargada.nombre)
            registrar_auditoria(
                db,
                gerente,
                Accion.CATEGORIA_CREADA,
                "categoria",
                creadas[precargada.nombre],
                {"nombre": precargada.nombre, "tipo": precargada.tipo, "precargada": True},
                origen=origen,
            )

    faltantes = [c.nombre.lower() for c in CATEGORIAS_PRECARGADAS if c.nombre not in creadas]
    if faltantes:
        filas = db.execute(
            select(func.lower(Categoria.nombre), Categoria.precargada).where(
                Categoria.gerente_id == gerente.id,
                func.lower(Categoria.nombre).in_(faltantes),
            )
        )
        existentes = {nombre: precargada for nombre, precargada in filas}
        for precargada in CATEGORIAS_PRECARGADAS:
            if precargada.nombre in creadas:
                continue
            if existentes.get(precargada.nombre.lower()):
                resultado.existentes.append(precargada.nombre)
            else:
                resultado.manuales.append(precargada.nombre)
    return resultado


def datos_distintos(gerente: Usuario, datos: DatosGerente) -> list[str]:
    """Campos indicados que no coinciden con los registrados. El correo se compara sin
    distinguir mayúsculas, como lo hace uq_usuario_correo."""
    distintos = []
    if datos.nombres is not None and datos.nombres != gerente.nombres:
        distintos.append("nombres")
    if datos.apellidos is not None and datos.apellidos != gerente.apellidos:
        distintos.append("apellidos")
    if datos.correo is not None and datos.correo.lower() != (gerente.correo or "").lower():
        distintos.append("correo")
    return distintos


def completar_existente(
    db: Session, gerente: Usuario, datos: DatosGerente, origen: Origen
) -> Inicializacion:
    validar_existente(gerente)
    categorias = precargar_categorias(db, gerente, origen)
    db.commit()
    return Inicializacion(gerente, False, categorias, datos_distintos(gerente, datos))


def crear_gerente(
    db: Session, datos: DatosGerente, contrasena: str, origen: Origen
) -> Usuario | None:
    """Inserta el gerente y devuelve None si otro proceso ya creó ese username."""
    password_hash = hashear_contrasena(contrasena)
    try:
        with db.begin_nested():
            gerente_id = db.scalar(
                insert(Usuario)
                .values(
                    rol="gerente",
                    username=datos.username,
                    password_hash=password_hash,
                    nombres=datos.nombres,
                    apellidos=datos.apellidos,
                    correo=datos.correo,
                    estado="activa",
                    contrasena_inicial=True,
                )
                .on_conflict_do_nothing(index_elements=[func.lower(Usuario.username)])
                .returning(Usuario.id)
            )
    except IntegrityError as error:
        # Otra cuenta tomó el correo entre la consulta y el guardado. El mensaje del error no
        # se propaga: incluye los parámetros del INSERT, entre ellos el hash.
        if "uq_usuario_correo" not in str(error.orig):
            raise
        raise correo_en_uso() from None
    if gerente_id is None:
        return None

    gerente = db.get_one(Usuario, gerente_id)
    # Como en la creación de asistentes (TASK-13), el hash inicial queda en el historial.
    db.add(HistorialContrasena(usuario_id=gerente.id, password_hash=password_hash))
    registrar_auditoria(
        db,
        gerente,
        Accion.CUENTA_CREADA,
        "usuario",
        gerente.id,
        {"username": gerente.username, "rol": gerente.rol, "estado": gerente.estado},
        origen=origen,
    )
    return gerente


def inicializar_gerente(
    db: Session, datos: DatosGerente, contrasena: str | None, origen: Origen
) -> Inicializacion:
    """Crea o completa el gerente del username en una sola transacción y hace commit. La
    contraseña solo se usa si hay que crearlo: la de un gerente existente no se cambia."""
    existente = buscar_cuenta(db, datos.username, bloquear=True)
    if existente is not None:
        return completar_existente(db, existente, datos, origen)

    if contrasena is None:
        raise ValueError("Se necesita la contraseña para crear el gerente.")
    if datos.correo is not None and db.scalar(
        select(Usuario.id).where(func.lower(Usuario.correo) == datos.correo.lower())
    ):
        raise correo_en_uso()

    gerente = crear_gerente(db, datos, contrasena, origen)
    if gerente is None:
        # Una ejecución simultánea lo creó primero: se sigue como si ya existiera.
        existente = buscar_cuenta(db, datos.username, bloquear=True)
        if existente is None:
            raise RuntimeError("El gerente creado en paralelo no se encontró.")
        return completar_existente(db, existente, datos, origen)

    categorias = precargar_categorias(db, gerente, origen)
    db.commit()
    return Inicializacion(gerente, True, categorias)
