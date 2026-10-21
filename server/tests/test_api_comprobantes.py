"""Subida de comprobantes por la API (H24 CA01, CA06, CA09; TASK-84).

S3 se reemplaza por el cliente en memoria de la fixture s3 (conftest). Cada caso de error
comprueba también que no quedó archivo guardado ni comprobante registrado.
"""

import json
import uuid
from collections.abc import Iterator
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.seguridad import crear_token
from app.main import app
from app.models import Auditoria, Comprobante, ComprobanteDeuda, Deuda, Usuario
from app.services import archivos
from tests.conftest import DosGerentes, Equipo, S3EnMemoria, nueva_deuda, nuevo_comprobante
from tests.test_archivos import imagen, pdf

RUTA = "/api/v1/comprobantes"


@pytest.fixture
def cliente(db: Session) -> Iterator[TestClient]:
    app.dependency_overrides[get_db] = lambda: db
    yield TestClient(app)
    app.dependency_overrides.clear()


def cabecera(usuario: Usuario) -> dict[str, str]:
    return {"Authorization": f"Bearer {crear_token(usuario)}"}


def en_proceso(db: Session, equipo: Equipo, monto: str = "100.00", moneda: str = "PEN") -> Deuda:
    deuda = nueva_deuda(db, equipo.gerente, monto=monto, moneda=moneda, estado="en_proceso")
    deuda.pago_iniciado_por = equipo.asistente.id
    db.flush()
    return deuda


def subir(
    cliente: TestClient,
    usuario: Usuario,
    repartos: list[dict[str, Any]] | str,
    contenido: bytes | None = None,
) -> Any:
    deudas = repartos if isinstance(repartos, str) else json.dumps(repartos)
    return cliente.post(
        RUTA,
        headers=cabecera(usuario),
        files={"archivo": ("comprobante.png", contenido or imagen("PNG"), "image/png")},
        data={"deudas": deudas},
    )


def contar_comprobantes(db: Session) -> int:
    return db.scalar(select(func.count()).select_from(Comprobante)) or 0


def test_la_asistente_sube_el_comprobante_de_su_pago(
    cliente: TestClient, db: Session, dos_gerentes: DosGerentes, s3: S3EnMemoria
) -> None:
    equipo = dos_gerentes.uno
    deuda = en_proceso(db, equipo, monto="85.40")

    r = subir(cliente, equipo.asistente, [{"deuda_id": str(deuda.id)}])

    assert r.status_code == 201, r.json()
    cuerpo = r.json()
    assert (cuerpo["estado"], cuerpo["moneda"], cuerpo["archivo_tipo"]) == (
        "procesando",
        "PEN",
        "png",
    )
    # Sin monto_aplicado se aplica todo el saldo de la deuda.
    assert cuerpo["deudas"] == [{"deuda_id": str(deuda.id), "monto_aplicado": "85.40"}]
    assert "archivo_url" not in cuerpo
    db.refresh(deuda)
    assert deuda.estado == "por_validar"
    comprobante = db.get(Comprobante, uuid.UUID(cuerpo["id"]))
    assert comprobante is not None
    assert comprobante.archivo_url == f"comprobantes/{equipo.gerente.id}/{comprobante.id}.png"
    assert comprobante.archivo_url in s3.objetos
    assert comprobante.subido_por == equipo.asistente.id
    auditoria = db.scalar(select(Auditoria).where(Auditoria.entidad_id == comprobante.id))
    assert auditoria is not None and auditoria.accion == "comprobante_subido"
    assert auditoria.detalle["deudas"] == [{"deuda_id": str(deuda.id), "monto_aplicado": "85.40"}]


def test_el_gerente_adjunta_sin_iniciar_el_pago(
    cliente: TestClient, db: Session, dos_gerentes: DosGerentes, s3: S3EnMemoria
) -> None:
    equipo = dos_gerentes.uno
    deuda = nueva_deuda(db, equipo.gerente, estado="pagada_parcial")

    r = subir(cliente, equipo.gerente, [{"deuda_id": str(deuda.id), "monto_aplicado": "40.00"}])

    assert r.status_code == 201, r.json()
    db.refresh(deuda)
    assert (deuda.estado, deuda.pago_iniciado_por) == ("por_validar", equipo.gerente.id)
    assert deuda.pago_iniciado_en is not None


def test_la_asistente_inicia_el_pago_antes_de_adjuntar(
    cliente: TestClient, db: Session, dos_gerentes: DosGerentes, s3: S3EnMemoria
) -> None:
    equipo = dos_gerentes.uno
    deuda = nueva_deuda(db, equipo.gerente, estado="pendiente")

    r = subir(cliente, equipo.asistente, [{"deuda_id": str(deuda.id)}])

    assert (r.status_code, r.json()["code"]) == (409, "SIN_INTENTO")
    assert s3.objetos == {}
    assert contar_comprobantes(db) == 0


@pytest.mark.parametrize("estado", ["pagada", "anulada", "con_problema", "esperando_aprobacion"])
def test_estados_cerrados_o_bloqueados_no_admiten_comprobantes(
    cliente: TestClient, db: Session, dos_gerentes: DosGerentes, s3: S3EnMemoria, estado: str
) -> None:
    equipo = dos_gerentes.uno
    deuda = nueva_deuda(db, equipo.gerente, estado=estado)

    r = subir(cliente, equipo.gerente, [{"deuda_id": str(deuda.id)}])

    assert (r.status_code, r.json()["code"]) == (409, "ESTADO_NO_PERMITIDO")
    assert s3.objetos == {}


def test_un_comprobante_cubre_varias_deudas_y_una_deuda_varios(
    cliente: TestClient, db: Session, dos_gerentes: DosGerentes, s3: S3EnMemoria
) -> None:
    equipo = dos_gerentes.uno
    luz, agua = en_proceso(db, equipo, "120.00"), en_proceso(db, equipo, "60.00")

    primero = subir(
        cliente,
        equipo.asistente,
        [
            {"deuda_id": str(luz.id), "monto_aplicado": "70.00"},
            {"deuda_id": str(agua.id), "monto_aplicado": "60.00"},
        ],
    )
    assert primero.status_code == 201, primero.json()

    # La luz queda por validar con 50.00 sin cubrir: un segundo comprobante cubre el resto.
    segundo = subir(cliente, equipo.asistente, [{"deuda_id": str(luz.id)}], imagen("JPEG"))
    assert segundo.status_code == 201, segundo.json()
    assert segundo.json()["deudas"] == [{"deuda_id": str(luz.id), "monto_aplicado": "50.00"}]

    # Ya no queda nada por cubrir hasta que alguno se resuelva.
    tercero = subir(cliente, equipo.asistente, [{"deuda_id": str(luz.id)}], pdf())
    assert (tercero.status_code, tercero.json()["code"]) == (409, "SIN_SALDO")
    aplicado = db.scalar(
        select(func.sum(ComprobanteDeuda.monto_aplicado)).where(ComprobanteDeuda.deuda_id == luz.id)
    )
    assert aplicado == Decimal("120.00")


def test_lo_validado_ya_no_cuenta_como_saldo(
    cliente: TestClient, db: Session, dos_gerentes: DosGerentes, s3: S3EnMemoria
) -> None:
    equipo = dos_gerentes.uno
    deuda = en_proceso(db, equipo, "100.00")
    nuevo_comprobante(db, deuda, equipo.asistente, "30.00", estado="validado")
    nuevo_comprobante(db, deuda, equipo.asistente, "100.00", estado="rechazado")

    r = subir(cliente, equipo.asistente, [{"deuda_id": str(deuda.id)}])

    assert r.json()["deudas"][0]["monto_aplicado"] == "70.00"


def test_el_monto_aplicado_no_supera_el_saldo(
    cliente: TestClient, db: Session, dos_gerentes: DosGerentes, s3: S3EnMemoria
) -> None:
    equipo = dos_gerentes.uno
    deuda = en_proceso(db, equipo, "50.00")

    r = subir(cliente, equipo.asistente, [{"deuda_id": str(deuda.id), "monto_aplicado": "50.01"}])

    assert r.status_code == 422
    assert (r.json()["field"], r.json()["disponible"]) == ("deudas", "50.00")
    assert s3.objetos == {}


def test_las_deudas_de_un_comprobante_comparten_moneda(
    cliente: TestClient, db: Session, dos_gerentes: DosGerentes, s3: S3EnMemoria
) -> None:
    equipo = dos_gerentes.uno
    soles, dolares = en_proceso(db, equipo), en_proceso(db, equipo, moneda="USD")

    r = subir(
        cliente, equipo.asistente, [{"deuda_id": str(soles.id)}, {"deuda_id": str(dolares.id)}]
    )

    assert (r.status_code, r.json()["code"]) == (422, "MONEDA_DISTINTA")


def test_el_comprobante_toma_la_moneda_de_sus_deudas(
    cliente: TestClient, db: Session, dos_gerentes: DosGerentes, s3: S3EnMemoria
) -> None:
    equipo = dos_gerentes.uno
    deuda = en_proceso(db, equipo, moneda="USD")

    r = subir(cliente, equipo.asistente, [{"deuda_id": str(deuda.id)}])

    assert r.json()["moneda"] == "USD"


def test_la_deuda_de_otro_gerente_responde_404(
    cliente: TestClient, db: Session, dos_gerentes: DosGerentes, s3: S3EnMemoria
) -> None:
    propia = en_proceso(db, dos_gerentes.uno)
    ajena = en_proceso(db, dos_gerentes.dos)

    r = subir(
        cliente,
        dos_gerentes.uno.asistente,
        [{"deuda_id": str(propia.id)}, {"deuda_id": str(ajena.id)}],
    )

    assert (r.status_code, r.json()["code"]) == (404, "NO_ENCONTRADO")
    assert s3.objetos == {}
    db.refresh(propia)
    assert propia.estado == "en_proceso"


def test_el_mismo_archivo_dos_veces_indica_en_que_deuda_se_uso(
    cliente: TestClient, db: Session, dos_gerentes: DosGerentes, s3: S3EnMemoria
) -> None:
    equipo = dos_gerentes.uno
    primera, segunda = en_proceso(db, equipo), en_proceso(db, equipo)
    contenido = imagen("PNG", (50, 50))
    original = subir(cliente, equipo.asistente, [{"deuda_id": str(primera.id)}], contenido)

    r = subir(cliente, equipo.asistente, [{"deuda_id": str(segunda.id)}], contenido)

    assert (r.status_code, r.json()["code"]) == (409, "DUPLICADO")
    assert r.json()["comprobante_id"] == original.json()["id"]
    assert r.json()["deudas"] == [str(primera.id)]
    assert len(s3.objetos) == 1


def test_el_duplicado_de_otro_gerente_no_revela_sus_datos(
    cliente: TestClient, db: Session, dos_gerentes: DosGerentes, s3: S3EnMemoria
) -> None:
    contenido = imagen("PNG", (60, 60))
    ajena = en_proceso(db, dos_gerentes.dos)
    subir(cliente, dos_gerentes.dos.asistente, [{"deuda_id": str(ajena.id)}], contenido)
    propia = en_proceso(db, dos_gerentes.uno)

    r = subir(cliente, dos_gerentes.uno.asistente, [{"deuda_id": str(propia.id)}], contenido)

    assert r.status_code == 409
    assert r.json() == {
        "detail": "Este archivo no se puede usar como comprobante.",
        "code": "DUPLICADO",
        "field": "archivo",
    }


def test_un_archivo_rechazado_se_puede_volver_a_subir(
    cliente: TestClient, db: Session, dos_gerentes: DosGerentes, s3: S3EnMemoria
) -> None:
    equipo = dos_gerentes.uno
    deuda = en_proceso(db, equipo)
    contenido = imagen("PNG", (70, 70))
    primero = subir(cliente, equipo.asistente, [{"deuda_id": str(deuda.id)}], contenido)
    comprobante = db.get(Comprobante, uuid.UUID(primero.json()["id"]))
    assert comprobante is not None
    comprobante.estado = "rechazado"
    db.flush()

    r = subir(cliente, equipo.asistente, [{"deuda_id": str(deuda.id)}], contenido)

    assert r.status_code == 201, r.json()


def test_dos_subidas_simultaneas_del_mismo_archivo(
    cliente: TestClient,
    db: Session,
    dos_gerentes: DosGerentes,
    s3: S3EnMemoria,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """La otra subida se confirma entre la consulta y la inserción: el índice único responde 409
    y el archivo de esta subida se borra."""
    from app.services import comprobantes as servicio

    equipo = dos_gerentes.uno
    contenido = imagen("PNG", (80, 80))
    otra = subir(
        cliente, equipo.asistente, [{"deuda_id": str(en_proceso(db, equipo).id)}], contenido
    )
    original = servicio.duplicado
    llamadas: list[str] = []

    def sin_ver_la_otra(db: Session, hash_sha256: str, gerente_id: uuid.UUID) -> Any:
        llamadas.append(hash_sha256)
        return None if len(llamadas) == 1 else original(db, hash_sha256, gerente_id)

    monkeypatch.setattr(servicio, "duplicado", sin_ver_la_otra)

    r = subir(cliente, equipo.asistente, [{"deuda_id": str(en_proceso(db, equipo).id)}], contenido)

    assert (r.status_code, r.json()["code"]) == (409, "DUPLICADO")
    assert r.json()["comprobante_id"] == otra.json()["id"]
    assert len(s3.objetos) == 1


@pytest.mark.parametrize(
    ("deudas", "mensaje"),
    [
        ("no es json", "Indica las deudas como una lista de deuda_id y monto_aplicado."),
        ('{"deuda_id": "x"}', "Indica las deudas como una lista de deuda_id y monto_aplicado."),
        (
            '[{"deuda_id": "no-uuid"}]',
            "Indica las deudas como una lista de deuda_id y monto_aplicado.",
        ),
        ("[]", "Indica al menos una deuda."),
    ],
)
def test_un_reparto_mal_formado_responde_422(
    cliente: TestClient, dos_gerentes: DosGerentes, s3: S3EnMemoria, deudas: str, mensaje: str
) -> None:
    r = subir(cliente, dos_gerentes.uno.asistente, deudas)

    assert r.status_code == 422
    assert (r.json()["field"], r.json()["detail"]) == ("deudas", mensaje)


def test_una_deuda_repetida_en_el_reparto_responde_422(
    cliente: TestClient, db: Session, dos_gerentes: DosGerentes, s3: S3EnMemoria
) -> None:
    deuda = en_proceso(db, dos_gerentes.uno)

    r = subir(
        cliente,
        dos_gerentes.uno.asistente,
        [{"deuda_id": str(deuda.id)}, {"deuda_id": str(deuda.id)}],
    )

    assert (r.status_code, r.json()["detail"]) == (422, "Una deuda solo puede aparecer una vez.")


def test_un_archivo_invalido_no_se_guarda(
    cliente: TestClient, db: Session, dos_gerentes: DosGerentes, s3: S3EnMemoria
) -> None:
    deuda = en_proceso(db, dos_gerentes.uno)

    r = subir(cliente, dos_gerentes.uno.asistente, [{"deuda_id": str(deuda.id)}], b"MZ\x90\x00")

    assert (r.status_code, r.json()["field"]) == (422, "archivo")
    assert s3.objetos == {}
    assert contar_comprobantes(db) == 0


def test_si_s3_no_responde_no_se_registra_nada(
    cliente: TestClient, db: Session, dos_gerentes: DosGerentes, s3: S3EnMemoria
) -> None:
    deuda = en_proceso(db, dos_gerentes.uno)
    s3.falla = True

    r = subir(cliente, dos_gerentes.uno.asistente, [{"deuda_id": str(deuda.id)}])

    assert (r.status_code, r.json()["code"]) == (503, "ARCHIVO_NO_DISPONIBLE")
    assert contar_comprobantes(db) == 0
    db.refresh(deuda)
    assert deuda.estado == "en_proceso"


def test_sin_sesion_responde_401(cliente: TestClient, s3: S3EnMemoria) -> None:
    r = cliente.post(
        RUTA,
        files={"archivo": ("c.png", imagen("PNG"), "image/png")},
        data={"deudas": "[]"},
    )

    assert r.status_code == 401


def test_si_el_commit_falla_se_borra_el_archivo(s3: S3EnMemoria) -> None:
    class SesionQueFalla:
        def commit(self) -> None:
            raise RuntimeError("se cayó la base")

    s3.objetos["comprobantes/huerfano.png"] = (b"x", "image/png")

    with pytest.raises(RuntimeError):
        archivos.confirmar_con_archivo(SesionQueFalla(), "comprobantes/huerfano.png")  # type: ignore[arg-type]

    assert s3.objetos == {}
