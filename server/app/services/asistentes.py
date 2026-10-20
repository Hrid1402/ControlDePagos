"""Servicio para la creación y gestión de asistentes por parte del gerente (TASK-13 y TASK-14).

Gestiona la generación/validación de credenciales, disponibilidad de username,
la regla de una sola asistente activa por gerente y el ciclo de la cuenta: activar,
desactivar, eliminar y restablecer contraseña.

Toda operación sobre las asistentes bloquea primero la fila del gerente: dos solicitudes
simultáneas del mismo gerente se hacen en fila y nunca quedan dos cuentas activas. Después se
bloquean las asistentes y al final sus órdenes, el orden usuario -> orden_pago de
app/services/ordenes.py.
"""

import re
import unicodedata
import uuid
from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.core.dependencias import Origen
from app.core.errores import ErrorApi
from app.core.eventos import TipoEvento, avisar_cierre_sesion
from app.core.reglas import LARGO_MINIMO_USERNAME
from app.core.seguridad import generar_contrasena_segura, hashear_contrasena
from app.core.tiempo import ahora_lima
from app.models import ActivacionCuenta, OrdenPago, Usuario
from app.schemas.asistentes import CrearAsistenteEntrada, DisponibilidadUsernameSalida
from app.services.auditoria import Accion, diferencias, nombre_de, registrar_auditoria
from app.services.contrasenas import actualizar_contrasena
from app.services.notificaciones import TipoNotificacion, notificar
from app.services.ordenes import ESTADOS_PENDIENTES, publicar_evento_orden


def normalizar_texto(texto: str) -> str:
    """Convierte texto con tildes o caracteres especiales a ASCII sin acentos."""
    nfkd = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in nfkd if not unicodedata.combining(c)).lower()


def sugerir_username_disponible(db: Session, base: str) -> str:
    """Busca el primer nombre de usuario disponible agregando un sufijo numérico."""
    base_limpia = re.sub(r"[^a-z0-9._-]", "", normalizar_texto(base))[:20]
    if not base_limpia:
        base_limpia = "asistente"

    sufijo = 1
    while True:
        candidato = f"{base_limpia}{sufijo}"
        ocupado = db.scalar(
            select(Usuario.id).where(func.lower(Usuario.username) == candidato.lower())
        )
        if ocupado is None:
            return candidato
        sufijo += 1


# Partículas que forman parte del primer apellido: «De la Cruz» es un solo apellido.
PARTICULAS_APELLIDO = frozenset({"de", "del", "la", "las", "los", "y", "san", "santa"})


def primer_apellido(apellidos: str) -> str:
    """Primer apellido con sus partículas iniciales: «De la Cruz Pérez» da «delacruz»."""
    partes = normalizar_texto(apellidos).split()
    tomadas: list[str] = []
    for parte in partes:
        tomadas.append(parte)
        if parte not in PARTICULAS_APELLIDO:
            break
    return re.sub(r"[^a-z0-9]", "", "".join(tomadas))


def generar_username_base(nombres: str, apellidos: str) -> str:
    """CA05: formato corto, inicial del primer nombre y primer apellido, en minúsculas y sin
    tildes. «Lucía Mariana» «Gómez Flores» da «lgomez»."""
    nombre = re.sub(r"[^a-z0-9]", "", normalizar_texto(nombres))
    apellido = primer_apellido(apellidos)
    base = f"{nombre[:1]}{apellido}"[:25]
    return base or "asistente"


def generar_username_disponible(db: Session, nombres: str, apellidos: str) -> str:
    """Genera un username único a partir de nombres y apellidos; si está ocupado, o es más corto
    que el mínimo, se le agrega un número (CA05)."""
    base = generar_username_base(nombres, apellidos)
    ocupado = db.scalar(select(Usuario.id).where(func.lower(Usuario.username) == base.lower()))
    if ocupado is None and len(base) >= LARGO_MINIMO_USERNAME:
        return base
    return sugerir_username_disponible(db, base)


def verificar_disponibilidad_username(db: Session, username: str) -> DisponibilidadUsernameSalida:
    """Verifica si un username está libre para registrarse."""
    nombre_limpio = username.strip().lower()
    ocupado = db.scalar(select(Usuario.id).where(func.lower(Usuario.username) == nombre_limpio))
    if ocupado is None:
        return DisponibilidadUsernameSalida(disponible=True, username=username, sugerencia=None)

    sugerencia = sugerir_username_disponible(db, nombre_limpio)
    return DisponibilidadUsernameSalida(disponible=False, username=username, sugerencia=sugerencia)


def crear_asistente(
    db: Session,
    gerente: Usuario,
    datos: CrearAsistenteEntrada,
    origen: Origen,
) -> tuple[Usuario, str]:
    """Crea una asistente para el gerente, aplicando credenciales y activando según regla."""
    bloquear_gerente(db, gerente)

    # Determinar el username
    if datos.username:
        username_candidato = datos.username.strip()
        ocupado = db.scalar(
            select(Usuario.id).where(func.lower(Usuario.username) == username_candidato.lower())
        )
        if ocupado is not None:
            raise ErrorApi(
                409,
                "USERNAME_DUPLICADO",
                f"El nombre de usuario '{username_candidato}' ya está en uso.",
                "username",
            )
        username_final = username_candidato
    else:
        username_final = generar_username_disponible(db, datos.nombres, datos.apellidos)

    # Determinar la contraseña
    if datos.contrasena:
        contrasena_plana = datos.contrasena
    else:
        contrasena_plana = generar_contrasena_segura(12)

    # La cuenta nace inactiva; activar ahora es la misma activación de TASK-14, que reemplaza a
    # la actual cerrando su sesión y traspasando sus órdenes sin atender.
    asistente = Usuario(
        gerente_id=gerente.id,
        rol="asistente",
        username=username_final,
        password_hash=hashear_contrasena(contrasena_plana),
        nombres=datos.nombres.strip(),
        apellidos=datos.apellidos.strip(),
        estado="inactiva",
        contrasena_inicial=True,
    )
    db.add(asistente)
    db.flush()

    # Registrar auditoría de creación (sin incluir la contraseña)
    detalle_auditoria = {
        "username": asistente.username,
        "nombres": asistente.nombres,
        "apellidos": asistente.apellidos,
        "estado": "activa" if datos.activar_ahora else "inactiva",
    }
    registrar_auditoria(
        db,
        gerente,
        Accion.CUENTA_CREADA,
        "usuario",
        asistente.id,
        detalle_auditoria,
        origen=origen,
    )

    if datos.activar_ahora:
        activar_cuenta(db, gerente, asistente, bloquear_activa(db, gerente), origen)

    db.commit()
    db.refresh(asistente)
    return asistente, contrasena_plana


# --- Consulta (TASK-11) ---


def consulta_lista(gerente: Usuario) -> Select[Usuario]:
    """Cuentas del gerente sin las eliminadas: la activa primero (CA02) y luego de la más reciente
    a la más antigua. paginar agrega el id como desempate estable."""
    return consulta_asistentes(gerente).order_by(
        (Usuario.estado == "activa").desc(), Usuario.creado_en.desc()
    )


@dataclass(frozen=True)
class DetalleAsistente:
    asistente: Usuario
    historial: list[tuple[ActivacionCuenta, Usuario]]


def detalle_asistente(db: Session, gerente: Usuario, asistente_id: uuid.UUID) -> DetalleAsistente:
    """Cuenta del gerente con su historial de activaciones (CA17); ajena o eliminada, 404."""
    asistente = db.scalar(consulta_asistentes(gerente).where(Usuario.id == asistente_id))
    if asistente is None:
        raise ErrorApi(404, "NO_ENCONTRADO", "No se encontró el recurso solicitado.")
    filas = db.execute(
        select(ActivacionCuenta, Usuario)
        .join(Usuario, Usuario.id == ActivacionCuenta.realizada_por)
        .where(ActivacionCuenta.cuenta_id == asistente.id)
        .order_by(ActivacionCuenta.creado_en.desc(), ActivacionCuenta.id.desc())
    )
    return DetalleAsistente(asistente, [(evento, autor) for evento, autor in filas.tuples()])


# --- Ciclo de la cuenta (TASK-14) ---

AVISO_SIN_ASISTENTE = "No queda ninguna asistente activa: tú harás los pagos."


@dataclass(frozen=True)
class Activacion:
    activada: Usuario
    desactivada: Usuario | None = None
    ordenes_traspasadas: list[OrdenPago] = field(default_factory=list)
    repetido: bool = False


@dataclass(frozen=True)
class Desactivacion:
    asistente: Usuario
    sin_asistente_activa: bool
    ordenes_canceladas: list[OrdenPago] = field(default_factory=list)
    repetido: bool = False


def bloquear_gerente(db: Session, gerente: Usuario) -> None:
    """Serializa las operaciones del gerente sobre sus asistentes hasta el commit.

    FOR NO KEY UPDATE y no FOR UPDATE: otra transacción que inserta una fila con llave foránea al
    gerente, como la auditoría del restablecimiento por enlace, toma FOR KEY SHARE sobre esta fila.
    Con FOR UPDATE esperaría al gerente mientras el gerente espera a la asistente que ella tiene
    bloqueada, y PostgreSQL cortaría una de las dos por interbloqueo."""
    db.execute(select(Usuario.id).where(Usuario.id == gerente.id).with_for_update(key_share=True))


def consulta_asistentes(gerente: Usuario) -> Select[Usuario]:
    """Cuentas de asistente del gerente que no fueron eliminadas."""
    return select(Usuario).where(
        Usuario.gerente_id == gerente.id,
        Usuario.rol == "asistente",
        Usuario.eliminado_en.is_(None),
    )


def bloquear_asistente_propia(db: Session, gerente: Usuario, asistente_id: uuid.UUID) -> Usuario:
    """Asistente del gerente bloqueada y releída; si no existe, es ajena o fue eliminada, 404.
    Sin bloquear las llaves foráneas, como bloquear_gerente; sigue esperando al FOR SHARE con que
    app/services/ordenes.py relee a la asistente mientras ella responde una orden."""
    asistente = db.scalar(
        consulta_asistentes(gerente)
        .where(Usuario.id == asistente_id)
        .with_for_update(key_share=True)
        .execution_options(populate_existing=True)
    )
    if asistente is None:
        raise ErrorApi(404, "NO_ENCONTRADO", "No se encontró el recurso solicitado.")
    return asistente


def bloquear_activa(db: Session, gerente: Usuario) -> Usuario | None:
    return db.scalar(
        consulta_asistentes(gerente)
        .where(Usuario.estado == "activa")
        .with_for_update(key_share=True)
        .execution_options(populate_existing=True)
    )


def ordenes_sin_atender(db: Session, asistente: Usuario) -> list[OrdenPago]:
    """Órdenes urgentes que la asistente todavía no aceptó ni rechazó (CA14). Una aceptada ya
    tiene un intento de pago a su nombre y no se traspasa ni se cancela."""
    return list(
        db.scalars(
            select(OrdenPago)
            .where(
                OrdenPago.gerente_id == asistente.gerente_id,
                OrdenPago.asistente_id == asistente.id,
                OrdenPago.estado.in_(ESTADOS_PENDIENTES),
            )
            .order_by(OrdenPago.creado_en, OrdenPago.id)
            .with_for_update()
        )
    )


def registrar_cambio_estado(
    db: Session,
    gerente: Usuario,
    asistente: Usuario,
    accion: Accion,
    detalle: dict[str, object],
    origen: Origen,
) -> None:
    """Historial de activaciones del detalle (CA17) y auditoría del gerente."""
    db.add(
        ActivacionCuenta(
            cuenta_id=asistente.id,
            accion=accion.value.removeprefix("cuenta_"),
            realizada_por=gerente.id,
        )
    )
    registrar_auditoria(db, gerente, accion, "usuario", asistente.id, detalle, origen=origen)


def revocar_sesiones(db: Session, asistente: Usuario) -> None:
    """Invalida los tokens emitidos y cierra sus WebSocket después del commit (CA13)."""
    asistente.token_version += 1
    avisar_cierre_sesion(db, asistente.id)


def desactivar_cuenta(
    db: Session, gerente: Usuario, asistente: Usuario, motivo: str, origen: Origen
) -> None:
    asistente.estado = "inactiva"
    revocar_sesiones(db, asistente)
    registrar_cambio_estado(
        db, gerente, asistente, Accion.CUENTA_DESACTIVADA, {"motivo": motivo}, origen
    )
    # El índice de activa única se revisa fila por fila: la anterior debe quedar inactiva en la
    # base antes de activar otra.
    db.flush()


def activar_asistente(
    db: Session, gerente: Usuario, asistente_id: uuid.UUID, origen: Origen
) -> Activacion:
    """Activa la cuenta, desactiva la actual y le traspasa sus órdenes sin atender en una sola
    transacción (CA10 y CA14). Activar la que ya está activa no cambia nada."""
    bloquear_gerente(db, gerente)
    anterior = bloquear_activa(db, gerente)
    asistente = bloquear_asistente_propia(db, gerente, asistente_id)
    if asistente.estado == "activa":
        return Activacion(activada=asistente, repetido=True)

    activacion = activar_cuenta(db, gerente, asistente, anterior, origen)
    db.commit()
    return activacion


def activar_cuenta(
    db: Session, gerente: Usuario, asistente: Usuario, anterior: Usuario | None, origen: Origen
) -> Activacion:
    """Activa una cuenta inactiva sin confirmar: desactiva la anterior, ya bloqueada, y le
    traspasa sus órdenes sin atender. Quien llama bloqueó al gerente y hace el commit."""
    pendientes: list[OrdenPago] = []
    if anterior is not None:
        pendientes = ordenes_sin_atender(db, anterior)
        desactivar_cuenta(db, gerente, anterior, "reemplazada_por_otra_asistente", origen)

    asistente.estado = "activa"
    registrar_cambio_estado(
        db,
        gerente,
        asistente,
        Accion.CUENTA_ACTIVADA,
        {"reemplaza_a": anterior.id if anterior else None},
        origen,
    )

    for orden in pendientes:
        # La nueva asistente aún no la vio: vuelve a enviada para que TASK-64 la reenvíe.
        de = orden.asistente_id
        orden.asistente_id = asistente.id
        orden.estado = "enviada"
        orden.vista_en = None
        registrar_auditoria(
            db,
            gerente,
            Accion.ORDEN_TRASPASADA,
            "orden_pago",
            orden.id,
            {"deuda_id": orden.deuda_id, "de": de, "a": asistente.id},
            origen=origen,
        )
        publicar_evento_orden(db, orden, TipoEvento.ORDEN_NUEVA)

    return Activacion(activada=asistente, desactivada=anterior, ordenes_traspasadas=pendientes)


def desactivar_asistente(
    db: Session,
    gerente: Usuario,
    asistente_id: uuid.UUID,
    origen: Origen,
    ahora: datetime | None = None,
) -> Desactivacion:
    """Bloquea el acceso de la cuenta y cierra sus sesiones (CA11 y CA13). Como solo hay una
    activa, desactivarla deja al gerente sin asistente: sus órdenes sin atender se cancelan y se
    le avisa (CA12 y CA14). Desactivar una cuenta inactiva no cambia nada."""
    momento = ahora or ahora_lima()
    bloquear_gerente(db, gerente)
    asistente = bloquear_asistente_propia(db, gerente, asistente_id)
    if asistente.estado != "activa":
        return Desactivacion(
            asistente=asistente,
            sin_asistente_activa=bloquear_activa(db, gerente) is None,
            repetido=True,
        )

    pendientes = ordenes_sin_atender(db, asistente)
    desactivar_cuenta(db, gerente, asistente, "desactivada_por_gerente", origen)

    for orden in pendientes:
        orden.estado = "cancelada"
        orden.cancelada_en = momento
        registrar_auditoria(
            db,
            gerente,
            Accion.ORDEN_CANCELADA,
            "orden_pago",
            orden.id,
            {"deuda_id": orden.deuda_id, "motivo": "sin_asistente_activa"},
            origen=origen,
        )
        publicar_evento_orden(db, orden, TipoEvento.ORDEN_CANCELADA)

    if pendientes:
        cantidad = len(pendientes)
        canceladas = (
            "Se canceló 1 orden urgente"
            if cantidad == 1
            else f"Se cancelaron {cantidad} órdenes urgentes"
        )
        notificar(
            db,
            gerente,
            TipoNotificacion.ORDEN_URGENTE,
            "Órdenes canceladas",
            f"{canceladas} porque desactivaste a {nombre_de(asistente)} y no queda otra "
            "asistente activa.",
            urgente=True,
            clave_evento=f"ordenes_canceladas:{asistente.id}:{asistente.token_version}",
            ahora=momento,
        )

    db.commit()
    return Desactivacion(
        asistente=asistente, sin_asistente_activa=True, ordenes_canceladas=pendientes
    )


def eliminar_asistente(
    db: Session,
    gerente: Usuario,
    asistente_id: uuid.UUID,
    origen: Origen,
    ahora: datetime | None = None,
) -> None:
    """Baja lógica de una cuenta inactiva (CA15). La fila se conserva para que el historial y la
    auditoría sigan mostrando su nombre; el usuario tampoco se libera."""
    bloquear_gerente(db, gerente)
    asistente = bloquear_asistente_propia(db, gerente, asistente_id)
    if asistente.estado == "activa":
        raise ErrorApi(409, "CUENTA_ACTIVA", "Desactiva la cuenta antes de eliminarla.")

    asistente.eliminado_en = ahora or ahora_lima()
    registrar_cambio_estado(
        db,
        gerente,
        asistente,
        Accion.CUENTA_ELIMINADA,
        {"username": asistente.username, "nombre": nombre_de(asistente)},
        origen,
    )
    db.commit()


def restablecer_contrasena_asistente(
    db: Session, gerente: Usuario, asistente_id: uuid.UUID, origen: Origen
) -> tuple[Usuario, str]:
    """Genera una contraseña nueva que se muestra una sola vez y cierra sus sesiones (CA16).
    Vuelve a ser contraseña inicial y quita el bloqueo por intentos fallidos."""
    bloquear_gerente(db, gerente)
    asistente = bloquear_asistente_propia(db, gerente, asistente_id)

    contrasena_plana = generar_contrasena_segura(12)
    version = asistente.token_version
    actualizar_contrasena(db, asistente, contrasena_plana)
    asistente.contrasena_inicial = True
    asistente.intentos_fallidos = 0
    asistente.bloqueado_hasta = None
    avisar_cierre_sesion(db, asistente.id)

    registrar_auditoria(
        db,
        gerente,
        Accion.CONTRASENA_RESTABLECIDA,
        "usuario",
        asistente.id,
        diferencias({"token_version": version}, {"token_version": asistente.token_version}),
        origen=origen,
    )
    db.commit()
    db.refresh(asistente)
    return asistente, contrasena_plana
