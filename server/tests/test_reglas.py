import pytest
from pydantic import BaseModel, ValidationError

from app.core.reglas import ContrasenaNueva, Username, validar_contrasena
from app.core.seguridad import generar_contrasena_segura


class Entrada(BaseModel):
    username: Username
    contrasena: ContrasenaNueva


@pytest.mark.parametrize(
    "contrasena",
    ["Clave-segura-1", "Aa1.aaaa", "Ñandú#2026", "Con espacio 1!", "Aa1-" * 18],
)
def test_contrasena_valida(contrasena: str) -> None:
    assert validar_contrasena(contrasena) == contrasena


@pytest.mark.parametrize(
    ("contrasena", "motivo"),
    [
        ("Aa1-aaa", "al menos 8"),
        ("clave-segura-1", "mayúscula"),
        ("CLAVE-SEGURA-1", "mayúscula"),
        ("Clave-segura", "mayúscula"),
        ("ClaveSegura1", "mayúscula"),
        ("Clave segura 1", "mayúscula"),
        ("Aa1-" * 18 + "a", "demasiado larga"),
        # 52 caracteres pero 78 bytes: pasaba un límite contado en caracteres.
        ("Ññ1-" * 13, "demasiado larga"),
    ],
)
def test_contrasena_invalida_explica_el_motivo(contrasena: str, motivo: str) -> None:
    with pytest.raises(ValueError, match=motivo) as error:
        validar_contrasena(contrasena)
    assert contrasena not in str(error.value)


def test_la_contrasena_generada_cumple_las_reglas() -> None:
    for _ in range(50):
        validar_contrasena(generar_contrasena_segura())


@pytest.mark.parametrize("username", ["abc", "a" * 30, "ana.paz", "j_perez-2", "  con_bordes  "])
def test_username_valido(username: str) -> None:
    assert Entrada(username=username, contrasena="Clave-segura-1").username == username.strip()


@pytest.mark.parametrize("username", ["ab", "a" * 31, "dos palabras", "ñandu", "a@b.com", ""])
def test_username_invalido(username: str) -> None:
    with pytest.raises(ValidationError):
        Entrada(username=username, contrasena="Clave-segura-1")
