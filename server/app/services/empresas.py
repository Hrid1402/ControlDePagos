"""Empresas comunes del catálogo (H10 CA01 y CA02, TASK-33).

El catálogo inicial vive en la constante EMPRESAS_COMUNES y se copia a la tabla empresa con
sincronizar_empresas, que llama el comando administrativo pnpm init:gerente. La API lee siempre
la tabla: así un servicio de una empresa conocida guarda su empresa_id, como hará T03 cuando
cargue las empresas por zona.

Cada empresa tiene un UUID fijo para que la sincronización sea idempotente: la tabla no tiene
unicidad por nombre. patron_codigo es una expresión regular que debe cumplir el código de
suministro completo; se deja en None hasta tener el formato verificado con la empresa.
"""

import re
import unicodedata
import uuid
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models import Empresa


@dataclass(frozen=True)
class EmpresaComun:
    id: uuid.UUID
    nombre: str
    tipo_servicio: str
    patron_codigo: str | None = None


# Sin RUC ni patrón: se agregan solo cuando estén confirmados.
EMPRESAS_COMUNES = (
    EmpresaComun(uuid.UUID("5b1f3c9e-8d2a-4e71-9c4b-2a6f0e8d1b01"), "Hidrandina", "luz"),
    EmpresaComun(uuid.UUID("5b1f3c9e-8d2a-4e71-9c4b-2a6f0e8d1b02"), "Enel", "luz"),
    EmpresaComun(uuid.UUID("5b1f3c9e-8d2a-4e71-9c4b-2a6f0e8d1b03"), "Luz del Sur", "luz"),
    EmpresaComun(uuid.UUID("5b1f3c9e-8d2a-4e71-9c4b-2a6f0e8d1b04"), "Sedalib", "agua"),
    EmpresaComun(uuid.UUID("5b1f3c9e-8d2a-4e71-9c4b-2a6f0e8d1b05"), "Sedapal", "agua"),
    EmpresaComun(uuid.UUID("5b1f3c9e-8d2a-4e71-9c4b-2a6f0e8d1b06"), "Cálidda", "gas"),
    EmpresaComun(uuid.UUID("5b1f3c9e-8d2a-4e71-9c4b-2a6f0e8d1b07"), "Quavii", "gas"),
    EmpresaComun(
        uuid.UUID("5b1f3c9e-8d2a-4e71-9c4b-2a6f0e8d1b08"), "Movistar", "telecomunicaciones"
    ),
    EmpresaComun(uuid.UUID("5b1f3c9e-8d2a-4e71-9c4b-2a6f0e8d1b09"), "Claro", "telecomunicaciones"),
    EmpresaComun(uuid.UUID("5b1f3c9e-8d2a-4e71-9c4b-2a6f0e8d1b0a"), "Entel", "telecomunicaciones"),
    EmpresaComun(uuid.UUID("5b1f3c9e-8d2a-4e71-9c4b-2a6f0e8d1b0b"), "Bitel", "telecomunicaciones"),
)


@dataclass
class EmpresasSincronizadas:
    creadas: list[str] = field(default_factory=list)
    # Ya existían y se les aplicó el patrón nuevo de la constante.
    actualizadas: list[str] = field(default_factory=list)
    existentes: list[str] = field(default_factory=list)


def sincronizar_empresas(db: Session) -> EmpresasSincronizadas:
    """Crea las empresas comunes que falten y aplica los patrones nuevos de la constante. No
    cambia nombre ni tipo de una empresa ya creada, ni borra un patrón que la constante no
    tenga. Repetirla, incluso en paralelo, no duplica nada. No hace commit."""
    creadas = set(
        db.scalars(
            insert(Empresa)
            .values(
                [
                    {
                        "id": e.id,
                        "nombre": e.nombre,
                        "tipo_servicio": e.tipo_servicio,
                        "patron_codigo": e.patron_codigo,
                    }
                    for e in EMPRESAS_COMUNES
                ]
            )
            .on_conflict_do_nothing(index_elements=[Empresa.id])
            .returning(Empresa.id)
        )
    )

    resultado = EmpresasSincronizadas()
    for comun in EMPRESAS_COMUNES:
        if comun.id in creadas:
            resultado.creadas.append(comun.nombre)
            continue
        empresa = db.get_one(Empresa, comun.id)
        if comun.patron_codigo is not None and empresa.patron_codigo != comun.patron_codigo:
            empresa.patron_codigo = comun.patron_codigo
            resultado.actualizadas.append(comun.nombre)
        else:
            resultado.existentes.append(comun.nombre)
    db.flush()
    return resultado


def clave_catalogo(nombre: str) -> str:
    """Forma de comparar un nombre escrito a mano con el catálogo: sin acentos, sin distinguir
    mayúsculas y con los espacios colapsados. Calidda y CÁLIDDA son Cálidda."""
    descompuesto = unicodedata.normalize("NFKD", nombre)
    sin_acentos = "".join(c for c in descompuesto if not unicodedata.combining(c))
    return " ".join(sin_acentos.casefold().split())


def listar_empresas(db: Session, tipo_servicio: str | None = None) -> list[Empresa]:
    consulta = select(Empresa).order_by(Empresa.nombre, Empresa.id)
    if tipo_servicio is not None:
        consulta = consulta.where(Empresa.tipo_servicio == tipo_servicio)
    return list(db.scalars(consulta))


def empresa_del_catalogo(db: Session, nombre: str) -> Empresa | None:
    """Empresa registrada cuyo nombre coincide con el escrito a mano, si la hay."""
    clave = clave_catalogo(nombre)
    for empresa in db.scalars(select(Empresa).order_by(Empresa.id)):
        if clave_catalogo(empresa.nombre) == clave:
            return empresa
    return None


def cumple_patron(empresa: Empresa, codigo: str) -> bool:
    """Sin patrón cualquier código no vacío es válido (H10 SDD)."""
    if empresa.patron_codigo is None:
        return True
    return re.fullmatch(empresa.patron_codigo, codigo) is not None
