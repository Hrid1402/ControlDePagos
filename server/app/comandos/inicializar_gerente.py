"""Comando administrativo que crea el gerente y sus categorías precargadas (TASK-27).

También completa el catálogo de empresas comunes (TASK-33), que comparten todos los gerentes:
quien ya tenga su gerente lo vuelve a ejecutar para cargarlas.

Uso, desde la raíz del repositorio: pnpm init:gerente

Lee los datos de las variables de entorno del proceso, no del archivo .env: GERENTE_USERNAME,
GERENTE_CONTRASENA y, opcionales, GERENTE_NOMBRES, GERENTE_APELLIDOS y GERENTE_CORREO. Si falta
el username o la contraseña y hay una terminal, los pide; la contraseña se pide sin eco y dos
veces. La contraseña solo se necesita si hay que crear el gerente.

Nunca escribe la contraseña ni su hash: ni en la salida, ni en la auditoría, ni en el registro.

Códigos de salida: 0 creado o ya existente, 1 error inesperado, 2 dato inválido o faltante,
3 conflicto con una cuenta existente y 130 interrumpido.
"""

import getpass
import os
import sys
from collections.abc import Callable, Mapping
from contextlib import AbstractContextManager
from typing import TextIO

from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.core.dependencias import Origen
from app.core.reglas import validar_contrasena
from app.schemas.inicializacion import DatosGerente
from app.services.empresas import EmpresasSincronizadas, sincronizar_empresas
from app.services.inicializacion import (
    ConflictoInicializacion,
    Inicializacion,
    buscar_cuenta,
    inicializar_gerente,
    validar_existente,
)

EXITO = 0
ERROR_INESPERADO = 1
ENTRADA_INVALIDA = 2
CONFLICTO = 3
INTERRUMPIDO = 130

ORIGEN = Origen(dispositivo="comando inicializar_gerente", ip=None)

VARIABLES = {
    "username": "GERENTE_USERNAME",
    "nombres": "GERENTE_NOMBRES",
    "apellidos": "GERENTE_APELLIDOS",
    "correo": "GERENTE_CORREO",
}
VARIABLE_CONTRASENA = "GERENTE_CONTRASENA"

# Mensajes propios por campo: el error de Pydantic incluye el valor recibido.
MENSAJES_CAMPO = {
    "username": "debe tener de 3 a 30 caracteres: letras sin tildes, números, punto, guion "
    "o guion bajo.",
    "nombres": "solo admite letras, con tildes y ñ.",
    "apellidos": "solo admite letras, con tildes y ñ.",
    "correo": "no es un correo válido.",
}


class EntradaInvalida(Exception):
    """Falta un dato o no cumple las reglas. El mensaje nunca incluye la contraseña."""


class Consola:
    """Entrada y salida del comando, reemplazables en las pruebas."""

    def __init__(
        self,
        salida: TextIO | None = None,
        errores: TextIO | None = None,
        interactiva: bool | None = None,
        pedir: Callable[[str], str] = input,
        pedir_oculto: Callable[[str], str] = getpass.getpass,
    ) -> None:
        self.salida = salida or sys.stdout
        self.errores = errores or sys.stderr
        self.interactiva = sys.stdin.isatty() if interactiva is None else interactiva
        self.pedir = pedir
        self.pedir_oculto = pedir_oculto

    def escribir(self, linea: str) -> None:
        self.salida.write(linea + "\n")

    def error(self, linea: str) -> None:
        self.errores.write(linea + "\n")


def valor(entorno: Mapping[str, str], variable: str) -> str | None:
    """Valor de la variable; vacía cuenta como ausente, como en el .env.example."""
    texto = entorno.get(variable, "")
    return texto if texto.strip() else None


def leer_datos(entorno: Mapping[str, str], consola: Consola) -> DatosGerente:
    username = valor(entorno, VARIABLES["username"])
    if username is None:
        if not consola.interactiva:
            raise EntradaInvalida(f"Falta la variable {VARIABLES['username']}.")
        username = consola.pedir("Usuario del gerente: ")
    try:
        return DatosGerente(
            username=username,
            nombres=valor(entorno, VARIABLES["nombres"]),
            apellidos=valor(entorno, VARIABLES["apellidos"]),
            correo=valor(entorno, VARIABLES["correo"]),
        )
    except ValidationError as error:
        campos = [str(e["loc"][0]) for e in error.errors(include_input=False)]
        detalle = "; ".join(f"{c} {MENSAJES_CAMPO.get(c, 'no es válido.')}" for c in campos)
        raise EntradaInvalida(f"Datos inválidos: {detalle}") from None


def leer_contrasena(entorno: Mapping[str, str], consola: Consola) -> str:
    contrasena = entorno.get(VARIABLE_CONTRASENA) or None
    if contrasena is None:
        if not consola.interactiva:
            raise EntradaInvalida(f"Falta la variable {VARIABLE_CONTRASENA}.")
        contrasena = consola.pedir_oculto("Contraseña inicial: ")
        if consola.pedir_oculto("Repite la contraseña: ") != contrasena:
            raise EntradaInvalida("Las contraseñas no coinciden.")
    try:
        return validar_contrasena(contrasena)
    except ValueError as error:
        raise EntradaInvalida(str(error)) from None


def informar(resultado: Inicializacion, empresas: EmpresasSincronizadas, consola: Consola) -> None:
    username = resultado.gerente.username
    if resultado.creado:
        consola.escribir(f"Gerente '{username}' creado.")
    else:
        consola.escribir(
            f"Gerente '{username}' ya existía; no se modificaron su contraseña ni sus datos."
        )
    if resultado.datos_distintos:
        consola.escribir(
            "Los datos indicados difieren de los registrados y no se aplicaron: "
            + ", ".join(resultado.datos_distintos)
            + "."
        )
    categorias = resultado.categorias
    consola.escribir(
        f"Categorías precargadas: {len(categorias.creadas)} creadas, "
        f"{len(categorias.existentes)} ya existían."
    )
    if categorias.manuales:
        consola.escribir(
            "Ya había categorías propias con el nombre de una precargada y se dejaron como "
            "están: " + ", ".join(categorias.manuales) + "."
        )
    actualizadas = (
        f", {len(empresas.actualizadas)} con patrón nuevo" if empresas.actualizadas else ""
    )
    consola.escribir(
        f"Empresas comunes: {len(empresas.creadas)} creadas{actualizadas}, "
        f"{len(empresas.existentes)} ya existían."
    )


def ejecutar(
    entorno: Mapping[str, str],
    consola: Consola,
    fabrica: Callable[[], AbstractContextManager[Session]],
) -> int:
    datos = leer_datos(entorno, consola)
    with fabrica() as db:
        existente = buscar_cuenta(db, datos.username)
        contrasena = None
        if existente is None:
            contrasena = leer_contrasena(entorno, consola)
        else:
            # El conflicto se informa antes de pedir una contraseña que no se usaría.
            validar_existente(existente)
        resultado = inicializar_gerente(db, datos, contrasena, ORIGEN)
        # El catálogo es común a todos los gerentes: se completa en cada ejecución.
        empresas = sincronizar_empresas(db)
        db.commit()
    informar(resultado, empresas, consola)
    return EXITO


def main(
    entorno: Mapping[str, str] | None = None,
    consola: Consola | None = None,
    fabrica: Callable[[], AbstractContextManager[Session]] = SessionLocal,
) -> int:
    entorno = os.environ if entorno is None else entorno
    consola = consola or Consola()
    try:
        return ejecutar(entorno, consola, fabrica)
    except EntradaInvalida as error:
        consola.error(str(error))
        return ENTRADA_INVALIDA
    except ConflictoInicializacion as error:
        consola.error(f"{error} No se hizo ningún cambio.")
        return CONFLICTO
    except EOFError:
        consola.error("La entrada terminó antes de recibir los datos. No se hizo ningún cambio.")
        return ENTRADA_INVALIDA
    except KeyboardInterrupt:
        consola.error("Inicialización interrumpida. No se hizo ningún cambio.")
        return INTERRUMPIDO
    except SQLAlchemyError:
        # El texto del error incluye los parámetros de la consulta: no se muestra.
        consola.error("No se pudo completar la inicialización por un error de la base de datos.")
        return ERROR_INESPERADO


if __name__ == "__main__":
    sys.exit(main())
