from decimal import Decimal

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel, field_validator

from app.core.errores import ErrorApi, registrar_manejadores
from app.main import app

prueba = FastAPI()
registrar_manejadores(prueba)


class Pago(BaseModel):
    monto: Decimal


@prueba.get("/error-api")
def error_api() -> None:
    raise ErrorApi(409, "DUPLICADO", "Ya existe un servicio con ese código", "codigo_suministro")


@prueba.get("/error-api-con-datos")
def error_api_con_datos() -> None:
    raise ErrorApi(
        409,
        "DUPLICADO",
        "Ya existe una deuda de este servicio para ese periodo.",
        "periodo",
        datos={"deuda_existente": {"id": "d1", "monto": "10.50"}},
    )


@prueba.get("/validacion")
def validacion(edad: int) -> dict[str, int]:
    return {"edad": edad}


@prueba.post("/pagos")
def crear_pago(pago: Pago) -> dict[str, str]:
    return {"monto": str(pago.monto)}


@prueba.get("/falla")
def falla() -> None:
    raise RuntimeError("detalle interno")


cliente = TestClient(prueba, raise_server_exceptions=False)
cliente_app = TestClient(app)


def test_error_de_negocio_con_su_status_y_campo() -> None:
    r = cliente.get("/error-api")
    assert r.status_code == 409
    assert r.json() == {
        "detail": "Ya existe un servicio con ese código",
        "code": "DUPLICADO",
        "field": "codigo_suministro",
    }


def test_los_datos_opcionales_se_agregan_a_la_respuesta() -> None:
    r = cliente.get("/error-api-con-datos")
    assert r.status_code == 409
    assert r.json() == {
        "detail": "Ya existe una deuda de este servicio para ese periodo.",
        "code": "DUPLICADO",
        "field": "periodo",
        "deuda_existente": {"id": "d1", "monto": "10.50"},
    }


def test_sin_datos_la_respuesta_no_tiene_claves_adicionales() -> None:
    error = ErrorApi(409, "CONFLICTO", "Conflicto")
    assert error.datos == {}
    assert set(cliente.get("/error-api").json()) == {"detail", "code", "field"}


@pytest.mark.parametrize("clave", ["detail", "code", "field"])
def test_los_datos_no_reemplazan_las_claves_del_formato(clave: str) -> None:
    with pytest.raises(ValueError, match=clave):
        ErrorApi(409, "DUPLICADO", "Duplicado", datos={clave: "otro"})


def test_campo_obligatorio_responde_422_con_el_campo() -> None:
    r = cliente.get("/validacion")
    assert r.status_code == 422
    assert r.json() == {
        "detail": "Este campo es obligatorio.",
        "code": "VALIDACION",
        "field": "edad",
    }


def test_valor_invalido_responde_422_con_el_campo() -> None:
    r = cliente.get("/validacion", params={"edad": "abc"})
    assert r.status_code == 422
    assert r.json() == {"detail": "El valor no es válido.", "code": "VALIDACION", "field": "edad"}


def test_campo_del_cuerpo_sin_prefijo_de_ubicacion() -> None:
    r = cliente.post("/pagos", json={})
    assert r.status_code == 422
    assert r.json()["field"] == "monto"
    assert r.json()["detail"] == "Este campo es obligatorio."


def test_json_mal_formado_no_inventa_un_campo() -> None:
    r = cliente.post("/pagos", content="{mal", headers={"Content-Type": "application/json"})
    assert r.status_code == 422
    assert r.json() == {
        "detail": "El cuerpo de la solicitud no es un JSON válido.",
        "code": "VALIDACION",
        "field": None,
    }


def test_error_inesperado_no_expone_detalles() -> None:
    r = cliente.get("/falla")
    assert r.status_code == 500
    assert r.json() == {
        "detail": "Ocurrió un error inesperado. Intenta de nuevo.",
        "code": "ERROR_INTERNO",
        "field": None,
    }
    assert "detalle interno" not in r.text


def test_ruta_inexistente_de_la_api_responde_404() -> None:
    r = cliente_app.get("/api/v1/no-existe")
    assert r.status_code == 404
    assert r.json() == {
        "detail": "No se encontró el recurso solicitado.",
        "code": "NO_ENCONTRADO",
        "field": None,
    }


def test_metodo_no_permitido_responde_405() -> None:
    r = cliente_app.post("/health")
    assert r.status_code == 405
    assert r.json()["code"] == "METODO_NO_PERMITIDO"
    assert r.json()["detail"] == "Método no permitido."
    assert "GET" in r.headers["allow"]


class EntradaConErrorInterno(BaseModel):
    valor: str

    @field_validator("valor")
    @classmethod
    def validar(cls, valor: str) -> str:
        raise ValueError(f"Detalle interno con el dato recibido: {valor}")


@prueba.post("/validacion-interna")
def validacion_interna(datos: EntradaConErrorInterno) -> None:
    pass


def test_solo_los_motivos_seguros_se_exponen_en_validacion() -> None:
    r = cliente.post("/validacion-interna", json={"valor": "dato-confidencial"})
    assert r.status_code == 422
    assert r.json() == {
        "detail": "El valor no es válido.",
        "code": "VALIDACION",
        "field": "valor",
    }
    assert "dato-confidencial" not in r.text
    assert "Detalle interno" not in r.text
