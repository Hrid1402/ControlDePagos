"""Inicialización idempotente del gerente y sus categorías precargadas (TASK-27, H09 CA01 a CA03).

Las ejecuciones simultáneas, con transacciones reales, están en
test_inicializacion_concurrencia.py.
"""

import io
import json
import logging
import uuid
from collections.abc import Callable
from contextlib import AbstractContextManager, nullcontext
from datetime import UTC, datetime

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.comandos import inicializar_gerente as comando
from app.comandos.inicializar_gerente import Consola, main
from app.core.seguridad import verificar_contrasena
from app.models import Auditoria, Categoria, HistorialContrasena, Usuario
from app.schemas.inicializacion import DatosGerente
from app.services.acceso import iniciar_sesion
from app.services.auditoria import Accion
from app.services.inicializacion import (
    CATEGORIAS_PRECARGADAS,
    ConflictoInicializacion,
    inicializar_gerente,
)
from tests.conftest import DosGerentes

ORIGEN = comando.ORIGEN
CONTRASENA = "Clave-inicial-1"
OTRA = "Otra-clave-2"
USERNAME = "gerente_inicial"


def inicializar(
    db: Session, username: str = USERNAME, contrasena: str | None = CONTRASENA, **datos: str
):
    return inicializar_gerente(db, DatosGerente(username=username, **datos), contrasena, ORIGEN)


def gerentes_con(db: Session, username: str) -> list[Usuario]:
    return list(db.scalars(select(Usuario).where(func.lower(Usuario.username) == username.lower())))


def categorias_de(db: Session, gerente_id: uuid.UUID) -> list[Categoria]:
    return list(
        db.scalars(
            select(Categoria).where(Categoria.gerente_id == gerente_id).order_by(Categoria.id)
        )
    )


def auditoria_de(db: Session, gerente_id: uuid.UUID) -> list[Auditoria]:
    return list(db.scalars(select(Auditoria).where(Auditoria.gerente_id == gerente_id)))


def conteos(db: Session) -> tuple[int | None, ...]:
    return tuple(
        db.scalar(select(func.count()).select_from(modelo))
        for modelo in (Usuario, Categoria, Auditoria, HistorialContrasena)
    )


# Creación


def test_crea_el_gerente_activo_con_su_contrasena_inicial(db: Session) -> None:
    resultado = inicializar(db, nombres="Rosa", apellidos="Díaz", correo="rosa@ejemplo.pe")

    gerente = resultado.gerente
    assert resultado.creado
    assert (gerente.rol, gerente.estado, gerente.gerente_id) == ("gerente", "activa", None)
    assert (gerente.nombres, gerente.apellidos, gerente.correo) == (
        "Rosa",
        "Díaz",
        "rosa@ejemplo.pe",
    )
    assert gerente.contrasena_inicial
    assert gerente.token_version == 0
    assert verificar_contrasena(CONTRASENA, gerente.password_hash)


def test_nombres_apellidos_y_correo_son_opcionales(db: Session) -> None:
    gerente = inicializar(db).gerente

    assert (gerente.nombres, gerente.apellidos, gerente.correo) == (None, None, None)


def test_el_hash_inicial_queda_en_el_historial_como_en_tarea_13(db: Session) -> None:
    gerente = inicializar(db).gerente

    historial = list(
        db.scalars(
            select(HistorialContrasena.password_hash).where(
                HistorialContrasena.usuario_id == gerente.id
            )
        )
    )
    assert historial == [gerente.password_hash]


def test_h01_el_gerente_creado_ingresa_con_sus_credenciales(db: Session) -> None:
    inicializar(db)

    usuario = iniciar_sesion(db, USERNAME.upper(), CONTRASENA, ORIGEN)

    assert usuario.rol == "gerente"


def test_ca01_ca02_ca03_crea_las_precargadas_con_tipo_color_e_icono(db: Session) -> None:
    resultado = inicializar(db)

    categorias = {
        c.nombre: (c.tipo, c.color, c.icono, c.precargada, c.creado_por)
        for c in categorias_de(db, resultado.gerente.id)
    }
    assert categorias == {
        "Luz": ("servicio_variable", "#F59E0B", "pi-bolt", True, None),
        "Agua": ("servicio_variable", "#0EA5E9", "pi-eye-dropper", True, None),
        "Gas": ("servicio_variable", "#F97316", "pi-gauge", True, None),
        "Telefonía e internet": ("monto_fijo", "#8B5CF6", "pi-wifi", True, None),
        "Tarjeta de crédito": ("tarjeta", "#EF4444", "pi-credit-card", True, None),
        "Préstamo": ("prestamo", "#10B981", "pi-building-columns", True, None),
        "Otros": ("servicio_variable", "#64748B", "pi-tag", True, None),
    }
    assert resultado.categorias.creadas == [c.nombre for c in CATEGORIAS_PRECARGADAS]


def test_otro_username_crea_otro_gerente_con_sus_propias_categorias(db: Session) -> None:
    uno = inicializar(db, "gerente_uno_ini").gerente
    dos = inicializar(db, "gerente_dos_ini").gerente

    assert uno.id != dos.id
    assert len(categorias_de(db, uno.id)) == len(CATEGORIAS_PRECARGADAS)
    assert len(categorias_de(db, dos.id)) == len(CATEGORIAS_PRECARGADAS)


# Ejecución repetida


def test_repetir_no_duplica_nada_ni_cambia_contrasena_ni_datos(db: Session) -> None:
    primero = inicializar(db, nombres="Rosa", correo="rosa@ejemplo.pe")
    antes = conteos(db)
    hash_inicial = primero.gerente.password_hash

    segundo = inicializar(db, contrasena=OTRA, nombres="Otra", correo="otra@ejemplo.pe")

    assert not segundo.creado
    assert segundo.gerente.id == primero.gerente.id
    assert conteos(db) == antes
    assert segundo.gerente.password_hash == hash_inicial
    assert (segundo.gerente.nombres, segundo.gerente.correo) == ("Rosa", "rosa@ejemplo.pe")
    assert segundo.datos_distintos == ["nombres", "correo"]
    assert segundo.categorias.creadas == []
    assert segundo.categorias.existentes == [c.nombre for c in CATEGORIAS_PRECARGADAS]


def test_el_mismo_username_con_otras_mayusculas_es_el_mismo_gerente(db: Session) -> None:
    primero = inicializar(db)

    segundo = inicializar(db, USERNAME.upper(), contrasena=None)

    assert not segundo.creado
    assert gerentes_con(db, USERNAME) == [primero.gerente]


def test_un_gerente_existente_recibe_solo_las_precargadas_que_le_faltan(
    db: Session, dos_gerentes: DosGerentes
) -> None:
    gerente = dos_gerentes.uno.gerente
    db.add(
        Categoria(gerente_id=gerente.id, nombre="Luz", tipo="servicio_variable", precargada=True)
    )
    db.flush()

    resultado = inicializar(db, gerente.username, contrasena=None)

    assert not resultado.creado
    assert resultado.categorias.existentes == ["Luz"]
    assert "Luz" not in resultado.categorias.creadas
    assert len(categorias_de(db, gerente.id)) == len(CATEGORIAS_PRECARGADAS)
    assert len(categorias_de(db, dos_gerentes.dos.gerente.id)) == 0


def test_una_categoria_propia_con_el_nombre_de_una_precargada_se_deja_como_esta(
    db: Session, dos_gerentes: DosGerentes
) -> None:
    gerente = dos_gerentes.uno.gerente
    propia = Categoria(gerente_id=gerente.id, nombre="LUZ", tipo="monto_fijo", color="#000000")
    db.add(propia)
    db.flush()

    resultado = inicializar(db, gerente.username, contrasena=None)

    db.refresh(propia)
    assert resultado.categorias.manuales == ["Luz"]
    assert (propia.nombre, propia.tipo, propia.color, propia.precargada) == (
        "LUZ",
        "monto_fijo",
        "#000000",
        False,
    )
    assert len(categorias_de(db, gerente.id)) == len(CATEGORIAS_PRECARGADAS)


# Conflictos


def inactivo(usuario: Usuario) -> None:
    usuario.estado = "inactiva"


def eliminado(usuario: Usuario) -> None:
    usuario.estado = "inactiva"
    usuario.eliminado_en = datetime.now(UTC)


@pytest.mark.parametrize(
    ("de_quien", "cambio", "motivo"),
    [
        ("asistente", None, "asistente"),
        ("gerente", inactivo, "inactivo"),
        ("gerente", eliminado, "eliminada"),
    ],
)
def test_un_username_que_no_es_de_un_gerente_activo_es_conflicto_sin_cambios(
    db: Session,
    dos_gerentes: DosGerentes,
    de_quien: str,
    cambio: Callable[[Usuario], None] | None,
    motivo: str,
) -> None:
    cuenta = getattr(dos_gerentes.uno, de_quien)
    if cambio is not None:
        cambio(cuenta)
    db.flush()
    estado = (cuenta.estado, cuenta.eliminado_en, cuenta.password_hash)
    antes = conteos(db)

    with pytest.raises(ConflictoInicializacion, match=motivo):
        inicializar(db, cuenta.username.upper())

    db.refresh(cuenta)
    assert (cuenta.estado, cuenta.eliminado_en, cuenta.password_hash) == estado
    assert conteos(db) == antes


def test_un_correo_de_otra_cuenta_es_conflicto_sin_cambios(
    db: Session, dos_gerentes: DosGerentes
) -> None:
    dos_gerentes.uno.asistente.correo = "ocupado@ejemplo.pe"
    db.flush()
    antes = conteos(db)

    with pytest.raises(ConflictoInicializacion, match="correo"):
        inicializar(db, correo="OCUPADO@ejemplo.pe")

    assert conteos(db) == antes


# Auditoría


def test_audita_la_cuenta_y_cada_categoria_sin_la_contrasena_ni_el_hash(db: Session) -> None:
    gerente = inicializar(db).gerente

    eventos = auditoria_de(db, gerente.id)
    acciones = [e.accion for e in eventos]
    assert acciones.count(Accion.CUENTA_CREADA) == 1
    assert acciones.count(Accion.CATEGORIA_CREADA) == len(CATEGORIAS_PRECARGADAS)
    assert len(eventos) == 1 + len(CATEGORIAS_PRECARGADAS)
    cuenta = next(e for e in eventos if e.accion == Accion.CUENTA_CREADA)
    assert cuenta.detalle == {"username": USERNAME, "rol": "gerente", "estado": "activa"}
    assert (cuenta.usuario_id, cuenta.entidad, cuenta.entidad_id) == (
        gerente.id,
        "usuario",
        gerente.id,
    )
    assert cuenta.dispositivo == "comando inicializar_gerente"
    texto = json.dumps([e.detalle for e in eventos], ensure_ascii=False)
    assert CONTRASENA not in texto and gerente.password_hash not in texto and "$2b$" not in texto


def test_repetir_no_agrega_eventos_de_auditoria(db: Session) -> None:
    gerente = inicializar(db).gerente
    antes = len(auditoria_de(db, gerente.id))

    inicializar(db, contrasena=None)

    assert len(auditoria_de(db, gerente.id)) == antes


# Comando


class Entradas:
    """Respuestas de la terminal. Falla si se pide algo que no se esperaba."""

    def __init__(self, *respuestas: str) -> None:
        self.respuestas = list(respuestas)
        self.preguntas: list[str] = []

    def __call__(self, pregunta: str) -> str:
        self.preguntas.append(pregunta)
        if not self.respuestas:
            raise AssertionError(f"No se esperaba la pregunta {pregunta!r}.")
        return self.respuestas.pop(0)


class Terminal:
    def __init__(
        self,
        interactiva: bool = False,
        pedir: Entradas | None = None,
        oculto: Entradas | None = None,
    ) -> None:
        self.salida = io.StringIO()
        self.errores = io.StringIO()
        self.pedir = pedir or Entradas()
        self.oculto = oculto or Entradas()
        self.consola = Consola(self.salida, self.errores, interactiva, self.pedir, self.oculto)

    @property
    def texto(self) -> str:
        return self.salida.getvalue() + self.errores.getvalue()


def ejecutar(
    db: Session, entorno: dict[str, str], terminal: Terminal | None = None
) -> tuple[int, Terminal]:
    terminal = terminal or Terminal()

    def fabrica() -> AbstractContextManager[Session]:
        return nullcontext(db)

    return main(entorno, terminal.consola, fabrica), terminal


ENTORNO = {"GERENTE_USERNAME": USERNAME, "GERENTE_CONTRASENA": CONTRASENA}


def test_comando_crea_y_luego_no_cambia_nada(db: Session, caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG)

    codigo, primera = ejecutar(db, ENTORNO)
    antes = conteos(db)
    codigo_repetido, segunda = ejecutar(db, ENTORNO)

    assert (codigo, codigo_repetido) == (0, 0)
    assert primera.salida.getvalue() == (
        f"Gerente '{USERNAME}' creado.\nCategorías precargadas: 7 creadas, 0 ya existían.\n"
    )
    assert segunda.salida.getvalue() == (
        f"Gerente '{USERNAME}' ya existía; no se modificaron su contraseña ni sus datos.\n"
        "Categorías precargadas: 0 creadas, 7 ya existían.\n"
    )
    assert conteos(db) == antes
    [gerente] = gerentes_con(db, USERNAME)
    for texto in (primera.texto, segunda.texto, caplog.text):
        assert CONTRASENA not in texto and gerente.password_hash not in texto


def test_comando_informa_datos_distintos_y_categorias_propias(
    db: Session, dos_gerentes: DosGerentes
) -> None:
    gerente = dos_gerentes.uno.gerente
    db.add(Categoria(gerente_id=gerente.id, nombre="otros", tipo="monto_fijo"))
    db.flush()

    codigo, terminal = ejecutar(
        db, {"GERENTE_USERNAME": gerente.username, "GERENTE_NOMBRES": "Distinto"}
    )

    assert codigo == 0
    salida = terminal.salida.getvalue()
    assert "no se aplicaron: nombres." in salida
    assert "6 creadas, 0 ya existían" in salida
    assert "se dejaron como están: Otros." in salida


def test_comando_con_gerente_existente_no_pide_la_contrasena(
    db: Session, dos_gerentes: DosGerentes
) -> None:
    terminal = Terminal(interactiva=True)

    codigo, _ = ejecutar(db, {"GERENTE_USERNAME": dos_gerentes.uno.gerente.username}, terminal)

    assert codigo == 0
    assert terminal.oculto.preguntas == []


def test_comando_pide_los_datos_faltantes_sin_eco_y_con_confirmacion(db: Session) -> None:
    terminal = Terminal(
        interactiva=True, pedir=Entradas(USERNAME), oculto=Entradas(CONTRASENA, CONTRASENA)
    )

    codigo, _ = ejecutar(db, {}, terminal)

    assert codigo == 0
    assert terminal.pedir.preguntas == ["Usuario del gerente: "]
    assert terminal.oculto.preguntas == ["Contraseña inicial: ", "Repite la contraseña: "]
    [gerente] = gerentes_con(db, USERNAME)
    assert verificar_contrasena(CONTRASENA, gerente.password_hash)


def test_comando_rechaza_una_confirmacion_distinta(db: Session) -> None:
    terminal = Terminal(interactiva=True, oculto=Entradas(CONTRASENA, OTRA))

    codigo, _ = ejecutar(db, {"GERENTE_USERNAME": USERNAME}, terminal)

    assert codigo == 2
    assert terminal.errores.getvalue() == "Las contraseñas no coinciden.\n"
    assert gerentes_con(db, USERNAME) == []


@pytest.mark.parametrize(
    ("entorno", "mensaje"),
    [
        ({}, "Falta la variable GERENTE_USERNAME.\n"),
        ({"GERENTE_USERNAME": "   "}, "Falta la variable GERENTE_USERNAME.\n"),
        ({"GERENTE_USERNAME": USERNAME}, "Falta la variable GERENTE_CONTRASENA.\n"),
        (
            {"GERENTE_USERNAME": USERNAME, "GERENTE_CONTRASENA": ""},
            "Falta la variable GERENTE_CONTRASENA.\n",
        ),
    ],
)
def test_comando_sin_terminal_exige_las_variables(
    db: Session, entorno: dict[str, str], mensaje: str
) -> None:
    antes = conteos(db)

    codigo, terminal = ejecutar(db, entorno)

    assert codigo == 2
    assert terminal.errores.getvalue() == mensaje
    assert conteos(db) == antes


@pytest.mark.parametrize(
    ("contrasena", "motivo"),
    [
        ("Aa1-aaa", "al menos 8 caracteres"),
        ("clave-inicial-1", "mayúscula, minúscula, número y símbolo"),
        ("ClaveInicial1", "mayúscula, minúscula, número y símbolo"),
        ("Ññ1-" * 13, "demasiado larga"),
    ],
)
def test_comando_aplica_las_reglas_comunes_de_contrasena(
    db: Session, contrasena: str, motivo: str
) -> None:
    codigo, terminal = ejecutar(
        db, {"GERENTE_USERNAME": USERNAME, "GERENTE_CONTRASENA": contrasena}
    )

    assert codigo == 2
    assert motivo in terminal.errores.getvalue()
    assert contrasena not in terminal.texto
    assert gerentes_con(db, USERNAME) == []


@pytest.mark.parametrize(
    ("variable", "valor", "campo"),
    [
        ("GERENTE_USERNAME", "a" * 31, "username"),
        ("GERENTE_USERNAME", "dos palabras", "username"),
        ("GERENTE_NOMBRES", "Rosa2", "nombres"),
        ("GERENTE_APELLIDOS", "Díaz!", "apellidos"),
        ("GERENTE_CORREO", "no-es-correo", "correo"),
    ],
)
def test_comando_valida_cada_campo_sin_mostrar_su_valor(
    db: Session, variable: str, valor: str, campo: str
) -> None:
    antes = conteos(db)

    codigo, terminal = ejecutar(db, {**ENTORNO, variable: valor})

    assert codigo == 2
    assert terminal.errores.getvalue().startswith(f"Datos inválidos: {campo} ")
    assert valor not in terminal.texto
    assert conteos(db) == antes


def test_comando_toma_las_variables_opcionales_vacias_como_ausentes(db: Session) -> None:
    entorno = {**ENTORNO, "GERENTE_NOMBRES": "", "GERENTE_CORREO": ""}

    codigo, _ = ejecutar(db, entorno)

    assert codigo == 0
    [gerente] = gerentes_con(db, USERNAME)
    assert (gerente.nombres, gerente.correo) == (None, None)


def test_comando_con_username_de_asistente_es_conflicto_y_no_pide_contrasena(
    db: Session, dos_gerentes: DosGerentes
) -> None:
    terminal = Terminal(interactiva=True)
    antes = conteos(db)

    codigo, _ = ejecutar(db, {"GERENTE_USERNAME": dos_gerentes.uno.asistente.username}, terminal)

    assert codigo == 3
    assert terminal.errores.getvalue() == (
        "El usuario indicado pertenece a una cuenta de asistente. No se hizo ningún cambio.\n"
    )
    assert terminal.oculto.preguntas == []
    assert conteos(db) == antes


def test_comando_con_correo_en_uso_es_conflicto(db: Session, dos_gerentes: DosGerentes) -> None:
    dos_gerentes.uno.gerente.correo = "ocupado@ejemplo.pe"
    db.flush()

    codigo, terminal = ejecutar(db, {**ENTORNO, "GERENTE_CORREO": "ocupado@ejemplo.pe"})

    assert codigo == 3
    assert "correo" in terminal.errores.getvalue()
    assert gerentes_con(db, USERNAME) == []


def test_comando_ante_un_error_de_base_no_muestra_los_parametros(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fallar(*_: object) -> None:
        raise OperationalError("INSERT ...", {"password_hash": "$2b$12$secreto"}, Exception())

    monkeypatch.setattr(comando, "inicializar_gerente", fallar)

    codigo, terminal = ejecutar(db, ENTORNO)

    assert codigo == 1
    assert terminal.errores.getvalue() == (
        "No se pudo completar la inicialización por un error de la base de datos.\n"
    )
    assert "secreto" not in terminal.texto


@pytest.mark.parametrize(("error", "codigo"), [(KeyboardInterrupt, 130), (EOFError, 2)])
def test_comando_interrumpido_no_cambia_nada(
    db: Session, error: type[BaseException], codigo: int
) -> None:
    def interrumpir(_: str) -> str:
        raise error

    terminal = Terminal(interactiva=True)
    terminal.consola.pedir_oculto = interrumpir

    resultado, _ = ejecutar(db, {"GERENTE_USERNAME": USERNAME}, terminal)

    assert resultado == codigo
    assert "No se hizo ningún cambio." in terminal.errores.getvalue()
    assert gerentes_con(db, USERNAME) == []
