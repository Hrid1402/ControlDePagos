"""Reglas documentales de un comprobante (H24 CA04 y CA05, TASK-87).

evaluar compara los datos extraídos con las deudas de su reparto y decide el resultado, sin
tocar la base: la aplicación de abonos está en app/services/abonos.py. Se evalúa después de
descartar ilegible, duplicado, entidad desconocida y campos faltantes (app/services/validacion.py).

Orden de las reglas, la primera que aplica decide:
1. baja_confianza: algún campo clave leído con confianza menor a UMBRAL_CONFIANZA. Revisión.
2. Moneda distinta a la de las deudas: revisión ("datos que no coinciden"). No se convierte.
3. otra_deuda: el código no es el de ninguna deuda del reparto. Rechazado; quien llama busca una
   deuda del gerente que sí coincida para sugerirla.
4. Empresa distinta con el código correcto: revisión ("datos que no coinciden").
5. fecha_dudosa: pagado antes de la emisión de la deuda (o del inicio de su periodo si no tiene
   emisión) o después de subir el comprobante. Revisión.
6. Monto comparado con lo aplicado en el reparto, con tolerancia de 0,10 de la moneda:
   - Coincide: validado por lo aplicado.
   - monto_menor con una deuda: validado como pago parcial por el monto del comprobante.
   - monto_menor con varias deudas: revisión, porque no se sabe a cuál falta.
   - monto_mayor: revisión. El excedente no se aplica sin un reparto explícito.

Nunca se valida por el importe solamente: llegar a la regla 6 exige entidad conocida, código y
empresa de la deuda, moneda y fecha creíbles.
"""

import re
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal

from rapidfuzz import fuzz

from app.core.tiempo import zona_horaria
from app.ocr.extraccion import DatosComprobante, normalizar

UMBRAL_CONFIANZA = 0.8
UMBRAL_EMPRESA = 85
TOLERANCIA = Decimal("0.10")


@dataclass(frozen=True)
class DeudaReparto:
    """Lo que las reglas necesitan de cada deuda del reparto."""

    id: uuid.UUID
    moneda: str
    codigo: str
    empresas: list[str]
    desde: date
    monto_aplicado: Decimal


@dataclass(frozen=True)
class Decision:
    estado: str
    motivo: str | None
    observacion: str
    # Abono por deuda si el resultado es validado.
    aplicados: dict[uuid.UUID, Decimal] = field(default_factory=dict)


def normalizar_codigo(codigo: str) -> str:
    """Sin espacios ni guiones y en mayúsculas, igual que el extractor."""
    return re.sub(r"[\s-]", "", codigo).upper()


def misma_empresa(leida: str, empresas: list[str]) -> bool:
    """Similitud por conjunto de palabras: "HIDRANDINA S.A." coincide con "Hidrandina"."""
    texto = normalizar(leida)
    return any(fuzz.token_set_ratio(texto, normalizar(e)) >= UMBRAL_EMPRESA for e in empresas if e)


def dinero(moneda: str, monto: Decimal) -> str:
    return f"{moneda} {monto}"


def evaluar(
    datos: DatosComprobante,
    moneda: str,
    deudas: list[DeudaReparto],
    subido_en: datetime,
) -> Decision:
    """Resultado de las reglas. datos ya tiene todos sus campos clave."""
    assert datos.monto and datos.moneda and datos.fecha_pago and datos.empresa and datos.codigo
    claves = (datos.empresa, datos.codigo, datos.moneda, datos.monto, datos.fecha_pago)
    if min(c.confianza for c in claves) < UMBRAL_CONFIANZA:
        return Decision(
            "en_revision",
            "baja_confianza",
            "Algunos datos del comprobante se leyeron con poca seguridad: lo revisa el gerente.",
        )
    if datos.moneda.valor != moneda:
        return Decision(
            "en_revision",
            None,
            f"El comprobante está en {datos.moneda.valor} y la deuda en {moneda}: lo revisa el "
            "gerente.",
        )

    codigo = normalizar_codigo(datos.codigo.valor)
    coinciden = [d for d in deudas if normalizar_codigo(d.codigo) == codigo]
    if not coinciden:
        return Decision(
            "rechazado",
            "otra_deuda",
            "El código del comprobante no es el de la deuda. Revisa la deuda o adjunta el "
            "comprobante correcto.",
        )
    if not any(misma_empresa(datos.empresa.valor, d.empresas) for d in coinciden):
        return Decision(
            "en_revision",
            None,
            f"La empresa del comprobante ({datos.empresa.valor}) no coincide con la de la deuda: "
            "lo revisa el gerente.",
        )

    pagado = datos.fecha_pago.valor.astimezone(zona_horaria())
    desde = min(d.desde for d in deudas)
    if pagado.date() < desde or pagado > subido_en:
        return Decision(
            "en_revision",
            "fecha_dudosa",
            f"La fecha de pago ({pagado:%d/%m/%Y}) no corresponde a la deuda: lo revisa el "
            "gerente.",
        )

    monto = datos.monto.valor
    total = sum((d.monto_aplicado for d in deudas), Decimal(0))
    if monto > total + TOLERANCIA:
        return Decision(
            "en_revision",
            "monto_mayor",
            f"El comprobante es por {dinero(moneda, monto)}, más que lo que cubre "
            f"({dinero(moneda, total)}): lo revisa el gerente.",
        )
    if monto < total - TOLERANCIA:
        if len(deudas) > 1:
            return Decision(
                "en_revision",
                "monto_menor",
                f"El comprobante es por {dinero(moneda, monto)}, menos que las deudas que cubre "
                f"({dinero(moneda, total)}): el gerente decide cómo repartirlo.",
            )
        (deuda,) = deudas
        return Decision(
            "validado",
            "monto_menor",
            f"Pago parcial de {dinero(moneda, monto)}: la deuda queda con saldo pendiente.",
            {deuda.id: monto},
        )
    return Decision(
        "validado",
        None,
        "Comprobante validado.",
        {d.id: d.monto_aplicado for d in deudas},
    )
