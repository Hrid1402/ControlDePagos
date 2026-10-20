"""Servicio de gestión de datos personales y política de privacidad (TASK-4).

Permite consultar y actualizar el perfil del usuario autenticado (CA11), validando
documento y correo únicos, e inmutabilidad del rol (CA09).
"""

from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core import politica
from app.core.dependencias import Origen
from app.core.errores import ErrorApi
from app.models import Usuario
from app.schemas.usuarios import ActualizarPerfilEntrada, PerfilSalida
from app.services.auditoria import Accion, diferencias, registrar_auditoria
from app.services.cuenta import cambios_restantes


def perfil_de(db: Session, usuario: Usuario) -> PerfilSalida:
    """Perfil con los datos que Mi cuenta necesita además de la fila: cambios de usuario que
    quedan en el mes (CA07), si usa la contraseña inicial (CA18) y la política vigente (CA10)."""
    return PerfilSalida(
        id=usuario.id,
        username=usuario.username,
        rol=usuario.rol,
        nombres=usuario.nombres,
        apellidos=usuario.apellidos,
        celular=usuario.celular,
        correo=usuario.correo,
        tipo_documento=usuario.tipo_documento,
        numero_documento=usuario.numero_documento,
        politica_version=usuario.politica_version,
        politica_aceptada_en=usuario.politica_aceptada_en,
        cambios_restantes=cambios_restantes(db, usuario),
        contrasena_inicial=usuario.contrasena_inicial,
        politica_vigente=politica.VERSION,
    )


def actualizar_perfil(
    db: Session,
    usuario: Usuario,
    datos: ActualizarPerfilEntrada,
    origen: Origen,
) -> Usuario:
    """Actualiza los datos personales del usuario y registra el evento en auditoría."""
    correo_limpio = datos.correo.strip() if datos.correo and datos.correo.strip() else None

    # Verificar si el documento ya está registrado por otro usuario
    if datos.numero_documento and datos.numero_documento != usuario.numero_documento:
        existente_doc = db.scalar(
            select(Usuario).where(
                Usuario.numero_documento == datos.numero_documento,
                Usuario.id != usuario.id,
            )
        )
        if existente_doc is not None:
            raise ErrorApi(
                409,
                "DOCUMENTO_DUPLICADO",
                "Ya existe un usuario con este número de documento.",
                "numero_documento",
            )

    # Verificar si el correo ya está registrado por otro usuario
    if correo_limpio and correo_limpio.lower() != (usuario.correo or "").lower():
        existente_correo = db.scalar(
            select(Usuario).where(
                func.lower(Usuario.correo) == correo_limpio.lower(),
                Usuario.id != usuario.id,
            )
        )
        if existente_correo is not None:
            raise ErrorApi(
                409,
                "CORREO_DUPLICADO",
                "Ya existe un usuario con este correo electrónico.",
                "correo",
            )

    anterior = {
        "nombres": usuario.nombres,
        "apellidos": usuario.apellidos,
        "celular": usuario.celular,
        "correo": usuario.correo,
        "tipo_documento": usuario.tipo_documento,
        "numero_documento": usuario.numero_documento,
        "politica_version": usuario.politica_version,
    }

    usuario.nombres = datos.nombres
    usuario.apellidos = datos.apellidos
    usuario.celular = datos.celular
    if datos.correo is not None:
        usuario.correo = correo_limpio
    if datos.tipo_documento is not None:
        usuario.tipo_documento = datos.tipo_documento
    if datos.numero_documento is not None:
        usuario.numero_documento = datos.numero_documento
    if datos.politica_version is not None:
        usuario.politica_version = datos.politica_version
        usuario.politica_aceptada_en = datetime.now(UTC)

    nuevo = {
        "nombres": usuario.nombres,
        "apellidos": usuario.apellidos,
        "celular": usuario.celular,
        "correo": usuario.correo,
        "tipo_documento": usuario.tipo_documento,
        "numero_documento": usuario.numero_documento,
        "politica_version": usuario.politica_version,
    }

    cambios = diferencias(anterior, nuevo)
    if cambios:
        registrar_auditoria(
            db,
            usuario,
            Accion.PERFIL_ACTUALIZADO,
            "usuario",
            usuario.id,
            cambios,
            origen=origen,
        )

    db.commit()
    db.refresh(usuario)
    return usuario


def aceptar_politica(
    db: Session,
    usuario: Usuario,
    version: str,
    origen: Origen,
) -> Usuario:
    """Registra la aceptación de la política vigente (CA10). Aceptar otra versión es un 409: el
    usuario vio un texto que ya no rige y debe leer el vigente."""
    if version != politica.VERSION:
        raise ErrorApi(
            409,
            "POLITICA_DESACTUALIZADA",
            "La política de privacidad cambió. Lee la versión vigente para aceptarla.",
            "version",
        )
    usuario.politica_version = version
    usuario.politica_aceptada_en = datetime.now(UTC)

    registrar_auditoria(
        db,
        usuario,
        Accion.POLITICA_ACEPTADA,
        "usuario",
        usuario.id,
        {"version": version},
        origen=origen,
    )

    db.commit()
    db.refresh(usuario)
    return usuario
