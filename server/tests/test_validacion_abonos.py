"""Validación completa del comprobante y sus abonos (H24 CA04 y CA05, TASK-87 y TASK-109).

Cada caso arma un comprobante en procesando sobre una deuda cuyo servicio coincide con la
constancia BCP del banco de ejemplos (Hidrandina, código 12345678, S/ 85.40 el 20/10/2026), y
aplica la lectura como lo hace el worker. Lo que coincide queda por confirmar y sus abonos se
aplican cuando el gerente lo aprueba. La última prueba usa transacciones reales y simultáneas.
"""

import threading
import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.core.dependencias import Origen
from app.core.tiempo import zona_horaria
from app.models import (
    Comprobante,
    ComprobanteDeuda,
    Deuda,
    Notificacion,
    Servicio,
    Usuario,
)
from app.ocr.motor import LecturaOcr, Linea
from app.services.revision_comprobantes import aprobar_comprobante
from app.services.saldo import saldo_de
from app.services.validacion import aplicar_lectura, bloquear_comprobante
from tests.conftest import DosGerentes, Equipo, nueva_categoria
from tests.ejemplos_comprobantes import EJEMPLOS
from tests.test_inicio_pago_concurrencia import borrar

LIMA = zona_horaria()
SUBIDO = datetime(2026, 10, 20, 12, 0, tzinfo=LIMA)
BCP = next(e for e in EJEMPLOS if e.nombre == "bcp_app")


def constancia(
    monto: str = "85.40", codigo: str = "12345678", operacion: str = "00456789"
) -> LecturaOcr:
    """La constancia BCP del banco de ejemplos con otro monto, código u operación."""
    cambios = {"S/ 85.40": f"S/ {monto}", "12345678": codigo, "00456789": operacion}
    return LecturaOcr(
        [Linea(cambios.get(texto, texto), BCP.confianza) for texto in BCP.lineas], paginas=1
    )


def servicio_de(db: Session, gerente: Usuario, codigo: str = "12345678") -> Servicio:
    existente = db.scalar(
        select(Servicio).where(
            Servicio.gerente_id == gerente.id, Servicio.codigo_suministro == codigo
        )
    )
    if existente is not None:
        return existente
    servicio = Servicio(
        gerente_id=gerente.id,
        categoria_id=nueva_categoria(db, gerente).id,
        empresa_nombre="Hidrandina",
        codigo_suministro=codigo,
    )
    db.add(servicio)
    db.flush()
    return servicio


def deuda_de(
    db: Session,
    gerente: Usuario,
    monto: str = "85.40",
    periodo: date = date(2026, 10, 1),
    codigo: str = "12345678",
) -> Deuda:
    deuda = Deuda(
        gerente_id=gerente.id,
        servicio_id=servicio_de(db, gerente, codigo).id,
        periodo=periodo,
        monto=Decimal(monto),
        estado="por_validar",
        fecha_vencimiento=periodo.replace(day=25),
    )
    db.add(deuda)
    db.flush()
    return deuda


def comprobante_de(
    db: Session, equipo: Equipo, repartos: list[tuple[Deuda, str]], estado: str = "procesando"
) -> Comprobante:
    comprobante = Comprobante(
        gerente_id=equipo.gerente.id,
        archivo_url=f"comprobantes/{uuid.uuid4()}.png",
        archivo_tipo="png",
        archivo_bytes=100,
        hash_sha256=uuid.uuid4().hex * 2,
        moneda="PEN",
        estado=estado,
        subido_por=equipo.asistente.id,
        creado_en=SUBIDO,
    )
    db.add(comprobante)
    db.flush()
    for deuda, monto in repartos:
        db.add(
            ComprobanteDeuda(
                comprobante_id=comprobante.id, deuda_id=deuda.id, monto_aplicado=Decimal(monto)
            )
        )
    for deuda, _ in repartos:
        deuda.pago_iniciado_por = equipo.asistente.id
        deuda.pago_iniciado_en = SUBIDO
    db.flush()
    return comprobante


def aplicar(db: Session, comprobante: Comprobante, lectura: LecturaOcr) -> Comprobante:
    bloqueado = bloquear_comprobante(db, comprobante.id)
    assert bloqueado is not None
    assert aplicar_lectura(db, bloqueado, lectura)
    db.flush()
    return bloqueado


def confirmar(db: Session, comprobante: Comprobante, gerente: Usuario) -> Comprobante:
    """El gerente valida el voucher con un clic, sin corregir el reparto."""
    aprobado = aprobar_comprobante(db, gerente, comprobante.id, origen=Origen(None, None))
    db.flush()
    return aprobado


def aplicado(db: Session, comprobante: Comprobante) -> list[Decimal]:
    return list(
        db.scalars(
            select(ComprobanteDeuda.monto_aplicado).where(
                ComprobanteDeuda.comprobante_id == comprobante.id
            )
        )
    )


def test_un_comprobante_correcto_se_valida_y_la_deuda_queda_pagada(
    db: Session, dos_gerentes: DosGerentes
) -> None:
    equipo = dos_gerentes.uno
    deuda = deuda_de(db, equipo.gerente)
    comprobante = comprobante_de(db, equipo, [(deuda, "85.40")])

    resultado = aplicar(db, comprobante, constancia())

    # La lectura coincide, pero no se valida sola: el gerente recibe el aviso para validarlo.
    assert (resultado.estado, resultado.motivo_codigo) == ("por_confirmar", None)
    assert resultado.datos_extraidos["observacion"] == (
        "El voucher coincide con la deuda. Falta que el gerente lo valide."
    )
    db.refresh(deuda)
    assert (deuda.estado, saldo_de(db, deuda)) == ("por_validar", Decimal("85.40"))
    (aviso,) = db.scalars(select(Notificacion))
    assert (aviso.tipo, aviso.usuario_id, aviso.titulo) == (
        "comprobante_en_revision",
        equipo.gerente.id,
        "Voucher por validar",
    )
    assert aviso.mensaje.endswith(
        "subió el voucher de Hidrandina 12345678 (octubre 2026). Revísalo y valídalo."
    )

    resultado = confirmar(db, resultado, equipo.gerente)

    assert resultado.estado == "validado"
    assert resultado.revisado_por == equipo.gerente.id
    db.refresh(deuda)
    assert (deuda.estado, deuda.pago_iniciado_por, deuda.pago_iniciado_en) == (
        "pagada",
        None,
        None,
    )
    assert saldo_de(db, deuda) == Decimal("0.00")
    (aviso,) = db.scalars(select(Notificacion).where(Notificacion.tipo == "deuda_pagada"))
    assert (aviso.usuario_id, aviso.deuda_id) == (equipo.gerente.id, deuda.id)


def test_un_monto_menor_deja_la_deuda_pagada_parcialmente_con_su_saldo(
    db: Session, dos_gerentes: DosGerentes
) -> None:
    equipo = dos_gerentes.uno
    deuda = deuda_de(db, equipo.gerente)
    comprobante = comprobante_de(db, equipo, [(deuda, "85.40")])

    resultado = aplicar(db, comprobante, constancia(monto="50.00"))

    assert (resultado.estado, resultado.motivo_codigo) == ("por_confirmar", "monto_menor")
    assert "Pago parcial de PEN 50.00" in resultado.datos_extraidos["observacion"]
    db.refresh(deuda)
    assert (deuda.estado, saldo_de(db, deuda)) == ("por_validar", Decimal("85.40"))

    # Al validarlo se aplica lo que leyó la validación, no el reparto de la subida.
    resultado = confirmar(db, resultado, equipo.gerente)

    assert aplicado(db, resultado) == [Decimal("50.00")]
    db.refresh(deuda)
    assert deuda.estado == "pagada_parcial"
    assert saldo_de(db, deuda) == Decimal("35.40")


def test_un_monto_mayor_queda_en_revision_sin_tocar_el_saldo(
    db: Session, dos_gerentes: DosGerentes
) -> None:
    equipo = dos_gerentes.uno
    deuda = deuda_de(db, equipo.gerente)
    comprobante = comprobante_de(db, equipo, [(deuda, "85.40")])

    resultado = aplicar(db, comprobante, constancia(monto="100.00"))

    assert (resultado.estado, resultado.motivo_codigo) == ("en_revision", "monto_mayor")
    db.refresh(deuda)
    assert (deuda.estado, saldo_de(db, deuda)) == ("por_validar", Decimal("85.40"))
    (aviso,) = db.scalars(select(Notificacion))
    assert (aviso.tipo, aviso.usuario_id) == ("comprobante_en_revision", equipo.gerente.id)


def test_un_comprobante_de_otra_deuda_sugiere_la_que_coincide(
    db: Session, dos_gerentes: DosGerentes
) -> None:
    equipo = dos_gerentes.uno
    agua = deuda_de(db, equipo.gerente, codigo="99887766")
    luz = deuda_de(db, equipo.gerente)
    luz.estado = "pendiente"
    comprobante = comprobante_de(db, equipo, [(agua, "85.40")])

    resultado = aplicar(db, comprobante, constancia())

    assert (resultado.estado, resultado.motivo_codigo) == ("rechazado", "otra_deuda")
    assert resultado.deuda_sugerida_id == luz.id
    assert "Hidrandina 12345678 (octubre 2026)" in resultado.datos_extraidos["observacion"]
    db.refresh(agua)
    assert agua.estado == "en_proceso"


def test_la_sugerencia_nunca_es_una_deuda_de_otro_gerente(
    db: Session, dos_gerentes: DosGerentes
) -> None:
    deuda_de(db, dos_gerentes.dos.gerente)
    propia = deuda_de(db, dos_gerentes.uno.gerente, codigo="99887766")
    comprobante = comprobante_de(db, dos_gerentes.uno, [(propia, "85.40")])

    resultado = aplicar(db, comprobante, constancia())

    assert resultado.motivo_codigo == "otra_deuda"
    assert resultado.deuda_sugerida_id is None
    assert "parece ser" not in resultado.datos_extraidos["observacion"]


def test_si_otro_comprobante_ya_cubrio_el_saldo_queda_en_revision(
    db: Session, dos_gerentes: DosGerentes
) -> None:
    equipo = dos_gerentes.uno
    deuda = deuda_de(db, equipo.gerente)
    comprobante = comprobante_de(db, equipo, [(deuda, "85.40")])
    # Otro comprobante de la misma deuda se validó mientras este esperaba.
    comprobante_de(db, equipo, [(deuda, "40.00")], estado="validado")

    resultado = aplicar(db, comprobante, constancia())

    assert (resultado.estado, resultado.motivo_codigo) == ("en_revision", "monto_mayor")
    assert aplicado(db, resultado) == [Decimal("85.40")]
    db.refresh(deuda)
    assert (deuda.estado, saldo_de(db, deuda)) == ("por_validar", Decimal("45.40"))


def test_con_otro_comprobante_activo_la_deuda_sigue_por_validar(
    db: Session, dos_gerentes: DosGerentes
) -> None:
    equipo = dos_gerentes.uno
    deuda = deuda_de(db, equipo.gerente, monto="100.00")
    comprobante = comprobante_de(db, equipo, [(deuda, "85.40")])
    comprobante_de(db, equipo, [(deuda, "14.60")])

    resultado = confirmar(db, aplicar(db, comprobante, constancia()), equipo.gerente)

    assert resultado.estado == "validado"
    db.refresh(deuda)
    assert (deuda.estado, saldo_de(db, deuda)) == ("por_validar", Decimal("14.60"))


def test_un_comprobante_para_dos_deudas_las_paga_a_ambas(
    db: Session, dos_gerentes: DosGerentes
) -> None:
    equipo = dos_gerentes.uno
    octubre = deuda_de(db, equipo.gerente, monto="50.00")
    setiembre = deuda_de(db, equipo.gerente, monto="35.40", periodo=date(2026, 9, 1))
    comprobante = comprobante_de(db, equipo, [(octubre, "50.00"), (setiembre, "35.40")])

    resultado = aplicar(db, comprobante, constancia())
    assert resultado.estado == "por_confirmar"
    resultado = confirmar(db, resultado, equipo.gerente)

    assert resultado.estado == "validado"
    for deuda in (octubre, setiembre):
        db.refresh(deuda)
        assert deuda.estado == "pagada"


def test_dos_comprobantes_validados_a_la_vez_no_cobran_dos_veces(
    publicados: list[object],
) -> None:
    """Dos comprobantes de la misma deuda (60 + 40 de 100) se leen y el gerente los valida a la
    vez: cada uno se aplica una vez, por turnos, y la deuda queda pagada con un solo aviso."""
    marca = uuid.uuid4().hex[:8]
    codigo = f"7{uuid.uuid4().int % 10**7:07d}"
    with SessionLocal() as db:
        gerente = Usuario(rol="gerente", username=f"conc_g_{marca}", password_hash="x")
        db.add(gerente)
        db.flush()
        asistente = Usuario(
            rol="asistente", gerente_id=gerente.id, username=f"conc_a_{marca}", password_hash="x"
        )
        db.add(asistente)
        db.flush()
        gerente_id = gerente.id
        deuda = deuda_de(db, gerente, monto="100.00", codigo=codigo)
        equipo = Equipo(gerente=gerente, asistente=asistente)
        primero = comprobante_de(db, equipo, [(deuda, "60.00")])
        segundo = comprobante_de(db, equipo, [(deuda, "40.00")])
        trabajos = [(primero.id, "60.00", "11110001"), (segundo.id, "40.00", "11110002")]
        deuda_id = deuda.id
        db.commit()
    try:
        barrera = threading.Barrier(len(trabajos))
        errores: list[BaseException] = []

        def validar(comprobante_id: uuid.UUID, monto: str, operacion: str) -> None:
            try:
                with SessionLocal() as db:
                    db.execute(text("SET LOCAL lock_timeout = '5s'"))
                    barrera.wait(timeout=10)
                    comprobante = db.get(Comprobante, comprobante_id)
                    assert comprobante is not None
                    leido = aplicar(db, comprobante, constancia(monto, codigo, operacion))
                    gerente = db.get(Usuario, gerente_id)
                    assert gerente is not None
                    confirmar(db, leido, gerente)
                    db.commit()
            except BaseException as error:
                errores.append(error)

        hilos = [threading.Thread(target=validar, args=trabajo) for trabajo in trabajos]
        for hilo in hilos:
            hilo.start()
        for hilo in hilos:
            hilo.join(timeout=20)
        assert errores == []

        with SessionLocal() as db:
            ids = [t[0] for t in trabajos]
            estados = list(db.scalars(select(Comprobante.estado).where(Comprobante.id.in_(ids))))
            deuda = db.get(Deuda, deuda_id)
            assert deuda is not None
            assert estados == ["validado", "validado"]
            assert (deuda.estado, saldo_de(db, deuda)) == ("pagada", Decimal("0.00"))
            avisos = db.scalar(
                select(func.count())
                .select_from(Notificacion)
                .where(Notificacion.tipo == "deuda_pagada", Notificacion.deuda_id == deuda_id)
            )
            assert avisos == 1
    finally:
        borrar([gerente_id])
