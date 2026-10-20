"""Servicio para la creación y gestión de asistentes por parte del gerente (TASK-13).

Gestiona la generación/validación de credenciales, disponibilidad de username,
y la regla de una sola asistente activa por gerente (TASK-14).
"""

import re
import unicodedata

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.dependencias import Origen
from app.core.errores import ErrorApi
from app.core.seguridad import generar_contrasena_segura, hashear_contrasena
from app.models import Usuario
from app.schemas.asistentes import CrearAsistenteEntrada, DisponibilidadUsernameSalida
from app.services.auditoria import Accion, registrar_auditoria


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


def generar_username_base(nombres: str, apellidos: str) -> str:
    """Genera un username base en formato nombre.apellido en minúsculas y sin acentos."""
    partes_nombre = normalizar_texto(nombres).split()
    partes_apellido = normalizar_texto(apellidos).split()

    primer_nombre = re.sub(r"[^a-z0-9]", "", partes_nombre[0]) if partes_nombre else "asistente"
    primer_apellido = (
        re.sub(r"[^a-z0-9]", "", partes_apellido[0]) if partes_apellido else "asistente"
    )

    base = f"{primer_nombre}.{primer_apellido}"[:25]
    return base


def generar_username_disponible(db: Session, nombres: str, apellidos: str) -> str:
    """Genera un username único y disponible a partir de nombres y apellidos."""
    base = generar_username_base(nombres, apellidos)
    ocupado = db.scalar(select(Usuario.id).where(func.lower(Usuario.username) == base.lower()))
    if ocupado is None:
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
    # Bloquear al gerente para serializar operaciones sobre sus asistentes (concurrencia)
    db.execute(select(Usuario.id).where(Usuario.id == gerente.id).with_for_update())

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

    # Regla: Una activa por gerente (TASK-14)
    if datos.activar_ahora:
        asistente_activa = db.scalar(
            select(Usuario).where(
                Usuario.gerente_id == gerente.id,
                Usuario.rol == "asistente",
                Usuario.estado == "activa",
                Usuario.eliminado_en.is_(None),
            )
        )
        if asistente_activa is not None:
            asistente_activa.estado = "inactiva"
            registrar_auditoria(
                db,
                gerente,
                Accion.CUENTA_DESACTIVADA,
                "usuario",
                asistente_activa.id,
                {"motivo": "reemplazada_por_nueva_asistente"},
                origen=origen,
            )
        nuevo_estado = "activa"
    else:
        nuevo_estado = "inactiva"

    asistente = Usuario(
        gerente_id=gerente.id,
        rol="asistente",
        username=username_final,
        password_hash=hashear_contrasena(contrasena_plana),
        nombres=datos.nombres.strip(),
        apellidos=datos.apellidos.strip(),
        estado=nuevo_estado,
        contrasena_inicial=True,
    )
    db.add(asistente)
    db.flush()

    # Registrar auditoría de creación (sin incluir la contraseña)
    detalle_auditoria = {
        "username": asistente.username,
        "nombres": asistente.nombres,
        "apellidos": asistente.apellidos,
        "estado": nuevo_estado,
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

    if nuevo_estado == "activa":
        registrar_auditoria(
            db,
            gerente,
            Accion.CUENTA_ACTIVADA,
            "usuario",
            asistente.id,
            {"motivo": "activada_al_crear"},
            origen=origen,
        )

    db.commit()
    db.refresh(asistente)
    return asistente, contrasena_plana
