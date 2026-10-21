"""Resultado de la validación automática de un comprobante (H24 CA03 y CA04).

El worker de OCR (app/workers/comprobantes.py) lee el archivo y llama a aplicar_lectura con el
comprobante bloqueado. Este módulo decide el resultado y lo aplica en la misma transacción:

- Sin texto o con confianza media menor a UMBRAL_ILEGIBLE: rechazado por ilegible.
- Con texto se extraen los datos de su entidad (app/ocr/extraccion.py) y se guardan.
- El mismo número de operación en la misma entidad que otro comprobante no rechazado: rechazado
  por duplicado. Si el otro es del mismo gerente, se indica en qué deudas se usó; si es ajeno, el
  mensaje es genérico (contrato H24, punto 5).
- Entidad no admitida o algún campo clave ausente: revisión del gerente con la explicación.
- Con los datos completos deciden las reglas documentales (app/services/reglas_comprobante.py):
  validado (completo o pago parcial), en revisión o rechazado por otra_deuda, con la deuda que
  parece corresponder como sugerencia. El validado aplica sus abonos (app/services/abonos.py).
- Si la lectura falla tras sus reintentos, sin_lectura lo deja en revisión con la explicación:
  el registro se conserva y el gerente decide.

Al resolver: el rechazado devuelve sus deudas a en_proceso (salvo que otro comprobante activo
siga cubriéndolas) para adjuntar otro o reemplazarlo; en revisión las deja en por_validar. Avisa
con una notificación (quien subió si se rechaza, el gerente si queda en revisión) y con el evento
comprobante_resultado a ambos. Todo sale después del commit.

Idempotencia: solo se resuelve un comprobante en procesando. Repetir la tarea o la recuperación
programada no cambia un resultado ya aplicado.
"""

import uuid
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.eventos import Evento, TipoEvento, publicar_tras_commit
from app.core.tiempo import ahora_lima
from app.models import Comprobante, ComprobanteDeuda, Deuda, Empresa, Servicio, Usuario
from app.ocr.extraccion import CampoClave, DatosComprobante, Entidad, extraer
from app.ocr.motor import LecturaOcr
from app.services.abonos import aplicar_abonos, otro_activo
from app.services.notificaciones import TipoNotificacion, notificar
from app.services.reglas_comprobante import DeudaReparto, evaluar, normalizar_codigo
from app.services.saldo import ESTADOS_CERRADOS

UMBRAL_ILEGIBLE = 0.6
# El texto completo de un comprobante cabe de sobra; el límite evita guardar basura de un PDF.
LARGO_MAXIMO_TEXTO = 20_000

ACCION_A_SEGUIR = {
    "ilegible": "No se pudo leer el comprobante. Toma otra foto con buena luz, sin cortes ni "
    "reflejos, y reemplázalo.",
    "duplicado": "Este comprobante ya se registró antes. Adjunta el comprobante de este pago.",
    "otra_deuda": "El comprobante corresponde a otra deuda. Revisa la deuda o adjunta el "
    "comprobante correcto.",
}
MENSAJE_FORMATO_DESCONOCIDO = (
    "No se reconoce el formato del comprobante: lo revisa el gerente. Se validan solos los de "
    "BCP, Interbank, BBVA, Scotiabank, Yape, Plin, Agente BCP y KasNet."
)
NOMBRES_CAMPOS = {
    CampoClave.EMPRESA: "la empresa",
    CampoClave.CODIGO: "el código de suministro",
    CampoClave.MONEDA: "la moneda",
    CampoClave.MONTO: "el monto",
    CampoClave.FECHA: "la fecha",
}
MESES = (
    "enero febrero marzo abril mayo junio julio agosto setiembre octubre noviembre diciembre"
).split()
MENSAJE_SIN_LECTURA = "No se pudo leer el archivo automáticamente: lo revisa el gerente."


def bloquear_comprobante(db: Session, comprobante_id: uuid.UUID) -> Comprobante | None:
    return db.scalar(
        select(Comprobante)
        .where(Comprobante.id == comprobante_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )


def deudas_de(db: Session, comprobante: Comprobante) -> list[Deuda]:
    """Deudas del reparto bloqueadas en orden de id, después del comprobante: el mismo orden que
    el reemplazo y la revisión del gerente."""
    return list(
        db.scalars(
            select(Deuda)
            .join(ComprobanteDeuda, ComprobanteDeuda.deuda_id == Deuda.id)
            .where(ComprobanteDeuda.comprobante_id == comprobante.id)
            .order_by(Deuda.id)
            .with_for_update(of=Deuda)
            .execution_options(populate_existing=True)
        )
    )


def guardar_lectura(comprobante: Comprobante, lectura: LecturaOcr) -> None:
    comprobante.texto_ocr = lectura.texto[:LARGO_MAXIMO_TEXTO]
    comprobante.confianza = Decimal(str(lectura.confianza)).quantize(
        Decimal("0.001"), ROUND_HALF_UP
    )
    comprobante.datos_extraidos = {
        **comprobante.datos_extraidos,
        "paginas": lectura.paginas,
        "lineas": len(lectura.lineas),
    }


def publicar_resultado(db: Session, comprobante: Comprobante, deudas: list[Deuda]) -> None:
    datos = {
        "comprobante_id": str(comprobante.id),
        "estado": comprobante.estado,
        "motivo_codigo": comprobante.motivo_codigo,
        "observacion": comprobante.datos_extraidos.get("observacion"),
        "deudas": [{"deuda_id": str(d.id), "estado": d.estado} for d in deudas],
    }
    for usuario_id in dict.fromkeys((comprobante.subido_por, comprobante.gerente_id)):
        publicar_tras_commit(db, usuario_id, Evento(TipoEvento.COMPROBANTE_RESULTADO, datos))


def avisar(db: Session, comprobante: Comprobante, deudas: list[Deuda], ahora: datetime) -> None:
    """Notifica según el resultado y publica comprobante_resultado. El validado no notifica aquí:
    cada deuda pagada avisa al gerente desde aplicar_abonos."""
    una_deuda = deudas[0].id if len(deudas) == 1 else None
    observacion = comprobante.datos_extraidos.get("observacion", "")
    if comprobante.estado == "rechazado":
        destinatario = db.get(Usuario, comprobante.subido_por)
        tipo, titulo = TipoNotificacion.COMPROBANTE_RECHAZADO, "Comprobante rechazado"
    elif comprobante.estado == "en_revision":
        destinatario = db.get(Usuario, comprobante.gerente_id)
        tipo, titulo = TipoNotificacion.COMPROBANTE_EN_REVISION, "Comprobante por revisar"
    else:
        destinatario = None
    if destinatario is not None:
        notificar(
            db,
            destinatario,
            tipo,
            titulo,
            observacion,
            deuda_id=una_deuda,
            clave_evento=f"{tipo.value}:{comprobante.id}",
            ahora=ahora,
        )
    publicar_resultado(db, comprobante, deudas)


def resolver(
    db: Session,
    comprobante: Comprobante,
    estado: str,
    motivo: str | None,
    observacion: str,
    ahora: datetime,
    aplicados: dict[uuid.UUID, Decimal] | None = None,
) -> None:
    """Aplica un resultado y avisa. El comprobante ya está bloqueado.

    validado aplica los abonos de aplicados; si el saldo de una deuda ya no alcanza (otro
    comprobante se validó antes), queda en revisión. rechazado devuelve sus deudas al intento
    vigente; en_revision las deja en por_validar."""
    deudas = deudas_de(db, comprobante)
    if estado == "validado":
        assert aplicados is not None
        sin_saldo = aplicar_abonos(db, comprobante, deudas, aplicados, ahora)
        if sin_saldo is not None:
            estado, motivo = "en_revision", "monto_mayor"
            observacion = (
                "Otro comprobante ya cubrió parte de la deuda y este supera su saldo: lo revisa "
                "el gerente."
            )
    comprobante.estado = estado
    comprobante.motivo_codigo = motivo
    comprobante.datos_extraidos = {**comprobante.datos_extraidos, "observacion": observacion}
    if estado == "rechazado":
        for deuda in deudas:
            if deuda.estado == "por_validar" and not otro_activo(db, deuda.id, comprobante.id):
                # Vuelve al intento vigente: se adjunta otro comprobante o se reemplaza este, y
                # los recordatorios de comprobante pendiente empiezan de nuevo (TASK-91).
                deuda.estado = "en_proceso"
                deuda.recordatorios_enviados = 0
    avisar(db, comprobante, deudas, ahora)


def guardar_datos(comprobante: Comprobante, datos: DatosComprobante) -> None:
    """Guarda los campos extraídos. El número de operación se guarda aparte, después de
    descartar el duplicado, porque tiene un índice único por entidad."""
    comprobante.entidad = datos.entidad.value
    comprobante.monto = datos.monto.valor if datos.monto else None
    comprobante.fecha_pago = datos.fecha_pago.valor if datos.fecha_pago else None
    comprobante.datos_extraidos = {**comprobante.datos_extraidos, **datos.a_json()}


def describir_deuda(db: Session, deuda_id: uuid.UUID) -> str:
    """Empresa, código y periodo de una deuda, para decir en qué deuda se usó un comprobante."""
    fila = db.execute(
        select(
            func.coalesce(Servicio.alias, Empresa.nombre, Servicio.empresa_nombre),
            Servicio.codigo_suministro,
            Deuda.periodo,
        )
        .join(Servicio, Servicio.id == Deuda.servicio_id)
        .outerjoin(Empresa, Empresa.id == Servicio.empresa_id)
        .where(Deuda.id == deuda_id)
    ).one()
    nombre, codigo, periodo = fila
    return f"{nombre or 'Servicio'} {codigo} ({MESES[periodo.month - 1]} {periodo.year})"


def operacion_repetida(
    db: Session, comprobante: Comprobante, entidad: Entidad, numero: str
) -> Comprobante | None:
    """Otro comprobante no rechazado con el mismo número de operación en la misma entidad. El
    bloqueo consultivo turna a dos comprobantes con el mismo número procesados a la vez: el
    segundo ve al primero y no choca con uq_comprobante_operacion."""
    clave = f"comprobante_operacion:{entidad.value}:{numero}"
    db.execute(select(func.pg_advisory_xact_lock(func.hashtextextended(clave, 0))))
    return db.scalar(
        select(Comprobante).where(
            Comprobante.entidad == entidad.value,
            Comprobante.numero_operacion == numero,
            Comprobante.estado != "rechazado",
            Comprobante.id != comprobante.id,
        )
    )


def explicar_duplicado(db: Session, comprobante: Comprobante, otro: Comprobante) -> str:
    if otro.gerente_id != comprobante.gerente_id:
        return ACCION_A_SEGUIR["duplicado"]
    deudas = [describir_deuda(db, r.deuda_id) for r in repartos_de(db, otro.id)]
    comprobante.datos_extraidos = {
        **comprobante.datos_extraidos,
        "duplicado_de": {
            "comprobante_id": str(otro.id),
            "deudas": [str(r.deuda_id) for r in repartos_de(db, otro.id)],
        },
    }
    return (
        f"Este comprobante ya se usó en {', '.join(deudas)}. Adjunta el comprobante de este pago."
    )


def repartos_de(db: Session, comprobante_id: uuid.UUID) -> list[ComprobanteDeuda]:
    return list(
        db.scalars(
            select(ComprobanteDeuda)
            .where(ComprobanteDeuda.comprobante_id == comprobante_id)
            .order_by(ComprobanteDeuda.deuda_id)
        )
    )


def explicar_faltantes(faltantes: list[CampoClave]) -> str:
    nombres = [NOMBRES_CAMPOS[f] for f in faltantes]
    lista = nombres[0] if len(nombres) == 1 else f"{', '.join(nombres[:-1])} y {nombres[-1]}"
    return f"No se pudo leer {lista} del comprobante: lo revisa el gerente."


def aplicar_lectura(
    db: Session, comprobante: Comprobante, lectura: LecturaOcr, ahora: datetime | None = None
) -> bool:
    """Aplica la lectura a un comprobante bloqueado. Devuelve False si ya estaba resuelto."""
    if comprobante.estado != "procesando":
        return False
    momento = ahora or ahora_lima()
    guardar_lectura(comprobante, lectura)
    if not lectura.lineas or lectura.confianza < UMBRAL_ILEGIBLE:
        resolver(db, comprobante, "rechazado", "ilegible", ACCION_A_SEGUIR["ilegible"], momento)
        return True
    datos = extraer(lectura)
    guardar_datos(comprobante, datos)
    if datos.entidad == Entidad.OTRA:
        resolver(db, comprobante, "en_revision", None, MENSAJE_FORMATO_DESCONOCIDO, momento)
        return True
    if datos.numero_operacion is not None:
        numero = datos.numero_operacion.valor
        otro = operacion_repetida(db, comprobante, datos.entidad, numero)
        if otro is not None:
            mensaje = explicar_duplicado(db, comprobante, otro)
            resolver(db, comprobante, "rechazado", "duplicado", mensaje, momento)
            return True
        comprobante.numero_operacion = numero
    if datos.faltantes:
        mensaje = explicar_faltantes(datos.faltantes)
        resolver(db, comprobante, "en_revision", None, mensaje, momento)
        return True
    decision = evaluar(
        datos, comprobante.moneda, reparto_para_reglas(db, comprobante), comprobante.creado_en
    )
    observacion = decision.observacion
    if decision.motivo == "otra_deuda":
        assert datos.codigo is not None
        sugerida = deuda_sugerida(db, comprobante, datos.codigo.valor)
        if sugerida is not None:
            comprobante.deuda_sugerida_id = sugerida
            observacion = (
                f"El comprobante parece ser de {describir_deuda(db, sugerida)}. Adjúntalo en esa "
                "deuda y sube aquí el comprobante correcto."
            )
    resolver(
        db, comprobante, decision.estado, decision.motivo, observacion, momento, decision.aplicados
    )
    return True


def reparto_para_reglas(db: Session, comprobante: Comprobante) -> list[DeudaReparto]:
    filas = db.execute(
        select(
            Deuda.id,
            Deuda.moneda,
            Deuda.fecha_emision,
            Deuda.periodo,
            ComprobanteDeuda.monto_aplicado,
            Servicio.codigo_suministro,
            Servicio.empresa_nombre,
            Servicio.alias,
            Empresa.nombre,
        )
        .join(ComprobanteDeuda, ComprobanteDeuda.deuda_id == Deuda.id)
        .join(Servicio, Servicio.id == Deuda.servicio_id)
        .outerjoin(Empresa, Empresa.id == Servicio.empresa_id)
        .where(ComprobanteDeuda.comprobante_id == comprobante.id)
        .order_by(Deuda.id)
    )
    return [
        DeudaReparto(
            id=fila.id,
            moneda=fila.moneda,
            codigo=fila.codigo_suministro,
            empresas=[e for e in (fila.nombre, fila.empresa_nombre, fila.alias) if e],
            desde=fila.fecha_emision or fila.periodo,
            monto_aplicado=fila.monto_aplicado,
        )
        for fila in filas
    ]


def deuda_sugerida(db: Session, comprobante: Comprobante, codigo: str) -> uuid.UUID | None:
    """Deuda abierta del mismo gerente cuyo código coincide con el del comprobante, fuera de su
    reparto. Nunca busca entre deudas de otro gerente (contrato H24, punto 5)."""
    en_reparto = select(ComprobanteDeuda.deuda_id).where(
        ComprobanteDeuda.comprobante_id == comprobante.id
    )
    codigo_servicio = func.upper(func.regexp_replace(Servicio.codigo_suministro, r"[\s-]", "", "g"))
    return db.scalar(
        select(Deuda.id)
        .join(Servicio, Servicio.id == Deuda.servicio_id)
        .where(
            Deuda.gerente_id == comprobante.gerente_id,
            Deuda.estado.not_in(ESTADOS_CERRADOS),
            Deuda.id.not_in(en_reparto),
            codigo_servicio == normalizar_codigo(codigo),
        )
        .order_by(Deuda.fecha_vencimiento, Deuda.id)
        .limit(1)
    )


def sin_lectura(db: Session, comprobante: Comprobante, ahora: datetime | None = None) -> bool:
    """La lectura falló tras sus reintentos: queda en revisión sin perder el registro."""
    if comprobante.estado != "procesando":
        return False
    resolver(db, comprobante, "en_revision", None, MENSAJE_SIN_LECTURA, ahora or ahora_lima())
    return True
