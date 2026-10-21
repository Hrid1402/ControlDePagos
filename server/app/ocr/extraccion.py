"""Extracción de datos de comprobantes por entidad con expresiones regulares (H24, TASK-86).

Sin IA: detecta la entidad por palabras clave y busca cada campo con la expresión de su entidad
(las etiquetas propias de la entidad primero y luego las comunes). Trabaja sobre las líneas del
OCR en minúsculas y sin tildes. Un campo puede estar en la misma línea que su etiqueta
("Monto pagado: S/ 85.40") o en la siguiente ("Monto pagado" y debajo "S/ 85.40").

Cada campo lleva la confianza del OCR de las líneas de donde salió (la menor), para que las reglas
(TASK-87) manden a revisión un dato leído con duda.

Campos clave (contrato H24): empresa, código, moneda, monto y fecha. Si falta alguno, o la entidad
no es de las admitidas, el comprobante va a revisión: nunca se aprueba por el importe solamente.
El número de operación no es clave, pero si está se usa para detectar duplicados.

Los formatos se escribieron con comprobantes de ejemplo inventados y anonimizados
(tests/ejemplos_comprobantes.py). Un formato nuevo se agrega con sus palabras clave en CLAVES,
sus etiquetas en ETIQUETAS y un ejemplo con su resultado esperado.
"""

import re
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from typing import Any

from app.core.tiempo import zona_horaria
from app.ocr.motor import LecturaOcr, Linea


class Entidad(StrEnum):
    """Valores de ck_comprobante_entidad."""

    BCP = "bcp"
    INTERBANK = "interbank"
    BBVA = "bbva"
    SCOTIABANK = "scotiabank"
    YAPE = "yape"
    PLIN = "plin"
    AGENTE_BCP = "agente_bcp"
    KASNET = "kasnet"
    OTRA = "otra"


class CampoClave(StrEnum):
    EMPRESA = "empresa"
    CODIGO = "codigo"
    MONEDA = "moneda"
    MONTO = "monto"
    FECHA = "fecha"


# Palabras clave en orden de prioridad: un voucher de Agente BCP o una constancia de Yape también
# dicen "BCP", por eso se buscan antes que el banco.
CLAVES: tuple[tuple[Entidad, re.Pattern[str]], ...] = tuple(
    (entidad, re.compile(patron))
    for entidad, patron in (
        (Entidad.AGENTE_BCP, r"agente\s*(?:de\s*)?bcp|agentebcp"),
        (Entidad.KASNET, r"kas\s*net"),
        (Entidad.YAPE, r"\byape|yapeaste"),
        (Entidad.PLIN, r"\bplin"),
        (Entidad.INTERBANK, r"interbank"),
        (Entidad.BBVA, r"\bbbva\b|bbva\s*continental"),
        (Entidad.SCOTIABANK, r"scotia\s*bank|scotiabank"),
        (Entidad.BCP, r"\bbcp\b|banco\s*de\s*credito"),
    )
)

# Etiquetas comunes por campo, de la más específica a la más general.
COMUNES: dict[str, list[str]] = {
    "operacion": [
        r"(?:n(?:ro|um(?:ero)?|o|°|º)?\.?\s*(?:de\s*)?|cod(?:igo)?\.?\s*(?:de\s*)?)operacion",
        r"operacion\s*(?:n(?:ro|°|º|o)\.?)?",
        r"\bop\.?\s*(?:n(?:ro|°|º)\.?)?",
    ],
    "monto": [
        r"(?:monto|importe|total)\s*(?:pagado|total|a\s*pagar|cobrado|de\s*la\s*operacion)?",
        r"pagaste|pago\s*total",
    ],
    "empresa": [r"empresa|beneficiario|entidad\s*(?:de\s*)?servicio|servicio|comercio"],
    "codigo": [
        r"(?:cod(?:igo)?\.?\s*(?:de\s*)?|n(?:ro|°|º)\.?\s*(?:de\s*)?)"
        r"(?:suministro|usuario|cliente|servicio|pago|contrato|abonado)",
        r"suministro|contrato|referencia|cod\.?\s*usuario",
    ],
    "fecha": [r"fecha\s*(?:y\s*hora)?\s*(?:de\s*(?:pago|operacion))?"],
}

# Etiquetas propias de cada entidad, que se prueban antes que las comunes.
ETIQUETAS: dict[Entidad, dict[str, list[str]]] = {
    Entidad.YAPE: {"monto": [r"yapeaste|pagaste\s*(?:a)?"], "empresa": [r"pago\s*de\s*servicio"]},
    Entidad.PLIN: {"monto": [r"plineaste|enviaste"]},
    Entidad.AGENTE_BCP: {
        "codigo": [r"cod\.?\s*(?:de\s*)?usuario|cod\.?\s*usu\.?"],
        "operacion": [r"nro\.?\s*oper\.?|oper\.?"],
    },
    Entidad.KASNET: {"codigo": [r"codigo\s*de\s*pago|cod\.?\s*pago"], "monto": [r"total"]},
    Entidad.INTERBANK: {"operacion": [r"codigo\s*de\s*operacion|cod\.?\s*operacion"]},
    Entidad.BBVA: {"monto": [r"importe\s*(?:pagado|cargado)?"], "codigo": [r"referencia"]},
    Entidad.SCOTIABANK: {"codigo": [r"codigo\s*de\s*servicio|cod\.?\s*servicio"]},
}

MONEDA = r"(?P<moneda>s/\.?|us\s*\$|\$|pen|usd|soles|dolares)"
NUMERO = r"(?P<numero>\d{1,3}(?:[,\s]\d{3})+(?:[.,]\d{1,2})?|\d+(?:[.,]\d{1,2})?)"
VALORES: dict[str, re.Pattern[str]] = {
    "operacion": re.compile(r"(?P<valor>\d[\d\s-]{3,20}\d)"),
    "monto": re.compile(rf"{MONEDA}?\s*{NUMERO}"),
    "empresa": re.compile(r"(?P<valor>[a-z][a-z0-9 .&'-]{1,60})"),
    "codigo": re.compile(r"(?P<valor>[a-z0-9][a-z0-9 -]{2,30})"),
}
MONTO_CON_MONEDA = re.compile(rf"{MONEDA}\s*{NUMERO}")
MESES = {
    "ene": 1,
    "feb": 2,
    "mar": 3,
    "abr": 4,
    "may": 5,
    "jun": 6,
    "jul": 7,
    "ago": 8,
    "set": 9,
    "sep": 9,
    "oct": 10,
    "nov": 11,
    "dic": 12,
}
# ISO primero: en 2026-10-12, el formato día/mes leería 26-10-12.
FECHAS = (
    re.compile(r"(?P<anio>\d{4})-(?P<mes>\d{2})-(?P<dia>\d{2})"),
    re.compile(r"(?<!\d)(?P<dia>\d{1,2})[/.-](?P<mes>\d{1,2})[/.-](?P<anio>\d{4}|\d{2})\b"),
    re.compile(
        r"(?P<dia>\d{1,2})\s*(?:de\s*)?(?P<mes>ene|feb|mar|abr|may|jun|jul|ago|set|sep|oct|nov|dic)"
        r"[a-z]*\.?\s*(?:de\s*|del\s*)?(?P<anio>\d{4})"
    ),
)
HORA = re.compile(
    r"(?P<hora>\d{1,2})\s*:\s*(?P<minuto>\d{2})(?::\d{2})?\s*(?P<meridiano>[ap]\.?\s*m\.?)?"
)
# Lo que puede ir entre una etiqueta y su valor en la misma línea.
SEPARADOR = " :.-#=|!¡"


@dataclass(frozen=True)
class Campo[T]:
    valor: T
    confianza: float


@dataclass(frozen=True)
class DatosComprobante:
    entidad: Entidad
    numero_operacion: Campo[str] | None = None
    monto: Campo[Decimal] | None = None
    moneda: Campo[str] | None = None
    fecha_pago: Campo[datetime] | None = None
    empresa: Campo[str] | None = None
    codigo: Campo[str] | None = None
    observaciones: list[str] = field(default_factory=list)

    @property
    def faltantes(self) -> list[CampoClave]:
        presentes = {
            CampoClave.EMPRESA: self.empresa,
            CampoClave.CODIGO: self.codigo,
            CampoClave.MONEDA: self.moneda,
            CampoClave.MONTO: self.monto,
            CampoClave.FECHA: self.fecha_pago,
        }
        return [clave for clave, campo in presentes.items() if campo is None]

    def a_json(self) -> dict[str, Any]:
        campos: dict[str, Any] = {}
        for nombre in ("numero_operacion", "monto", "moneda", "fecha_pago", "empresa", "codigo"):
            campo = getattr(self, nombre)
            if campo is not None:
                valor = campo.valor
                texto = valor.isoformat() if isinstance(valor, datetime) else str(valor)
                campos[nombre] = {"valor": texto, "confianza": round(campo.confianza, 3)}
        return {
            "entidad": self.entidad.value,
            "campos": campos,
            "faltantes": [f.value for f in self.faltantes],
        }


def normalizar(texto: str) -> str:
    """Minúsculas, sin tildes y con espacios simples, para comparar etiquetas."""
    descompuesto = unicodedata.normalize("NFKD", texto)
    sin_tildes = "".join(c for c in descompuesto if not unicodedata.combining(c))
    return " ".join(sin_tildes.lower().split())


def detectar_entidad(lineas: list[Linea]) -> Entidad:
    texto = "\n".join(linea.texto for linea in lineas)
    for entidad, patron in CLAVES:
        if patron.search(texto):
            return entidad
    return Entidad.OTRA


def etiqueta_de(entidad: Entidad, campo: str) -> re.Pattern[str]:
    patrones = ETIQUETAS.get(entidad, {}).get(campo, []) + COMUNES[campo]
    return re.compile("|".join(f"(?:{p})" for p in patrones))


def cualquier_etiqueta(entidad: Entidad) -> re.Pattern[str]:
    patrones = [p for campo in COMUNES for p in ETIQUETAS.get(entidad, {}).get(campo, [])]
    patrones += [p for lista in COMUNES.values() for p in lista]
    return re.compile("|".join(f"(?:{p})" for p in patrones))


def buscar(
    lineas: list[Linea],
    etiqueta: re.Pattern[str],
    valor: re.Pattern[str],
    otras: re.Pattern[str] | None = None,
) -> tuple[re.Match[str], float] | None:
    """Primer valor que sigue a la etiqueta en su línea o al comienzo de la siguiente. La línea
    siguiente no cuenta si empieza con otra etiqueta (otras): es otro campo, no este valor."""
    for i, linea in enumerate(lineas):
        for coincidencia in etiqueta.finditer(linea.texto):
            resto = linea.texto[coincidencia.end() :]
            encontrado = valor.search(resto)
            if encontrado and not resto[: encontrado.start()].strip(SEPARADOR):
                return encontrado, linea.confianza
            if not resto.strip(SEPARADOR) and i + 1 < len(lineas):
                siguiente = lineas[i + 1]
                if otras is not None and otras.match(siguiente.texto):
                    continue
                encontrado = valor.match(siguiente.texto)
                if encontrado:
                    return encontrado, min(linea.confianza, siguiente.confianza)
    return None


def a_decimal(numero: str) -> Decimal | None:
    """Admite 1,234.50, 1 234.50, 85.40, 85,40 y 85. La coma con dos decimales es decimal."""
    texto = numero.replace(" ", "")
    if "," in texto and "." in texto:
        texto = texto.replace(",", "")
    elif "," in texto:
        entero, decimales = texto.rsplit(",", 1)
        texto = (
            f"{entero.replace(',', '')}.{decimales}"
            if len(decimales) <= 2
            else texto.replace(",", "")
        )
    try:
        monto = Decimal(texto).quantize(Decimal("0.01"))
    except InvalidOperation:
        return None
    return monto if monto > 0 else None


def a_moneda(simbolo: str | None) -> str | None:
    if not simbolo:
        return None
    simbolo = simbolo.replace(" ", "")
    if simbolo.startswith(("s/", "pen", "soles")):
        return "PEN"
    return "USD"


def extraer_monto(
    lineas: list[Linea], entidad: Entidad
) -> tuple[Campo[Decimal] | None, Campo[str] | None]:
    resultado = buscar(
        lineas, etiqueta_de(entidad, "monto"), VALORES["monto"], cualquier_etiqueta(entidad)
    )
    if resultado is None:
        # Sin etiqueta solo vale un importe con su moneda, y solo si hay uno distinto: con dos
        # importes (monto y comisión, por ejemplo) no se adivina cuál es el pagado.
        candidatos = {
            (m.group("numero"), m.group("moneda"), linea.confianza)
            for linea in lineas
            for m in MONTO_CON_MONEDA.finditer(linea.texto)
        }
        if len({a_decimal(n) for n, _, _ in candidatos}) != 1:
            return None, moneda_del_texto(lineas)
        numero, simbolo, confianza = min(candidatos, key=lambda c: c[2])
    else:
        coincidencia, confianza = resultado
        numero, simbolo = coincidencia.group("numero"), coincidencia.group("moneda")
    monto = a_decimal(numero)
    moneda = a_moneda(simbolo)
    campo_moneda = Campo(moneda, confianza) if moneda else moneda_del_texto(lineas)
    return (Campo(monto, confianza) if monto else None), campo_moneda


def moneda_del_texto(lineas: list[Linea]) -> Campo[str] | None:
    """La moneda que aparece en el comprobante si es una sola."""
    halladas = {
        (a_moneda(m.group("moneda")), linea.confianza)
        for linea in lineas
        for m in MONTO_CON_MONEDA.finditer(linea.texto)
    }
    monedas = {moneda for moneda, _ in halladas if moneda}
    if len(monedas) != 1:
        return None
    (moneda,) = monedas
    return Campo(moneda, min(c for m, c in halladas if m == moneda))


def extraer_fecha(lineas: list[Linea], entidad: Entidad) -> Campo[datetime] | None:
    etiqueta = etiqueta_de(entidad, "fecha")
    # Primero las líneas con etiqueta de fecha y la siguiente; si no hay, todas.
    orden = [i for i, linea in enumerate(lineas) if etiqueta.search(linea.texto)]
    indices = [j for i in orden for j in (i, i + 1) if j < len(lineas)] or range(len(lineas))
    for i in indices:
        linea = lineas[i]
        for patron in FECHAS:
            encontrada = patron.search(linea.texto)
            if encontrada is None:
                continue
            fecha = construir_fecha(
                encontrada, linea, lineas[i + 1] if i + 1 < len(lineas) else None
            )
            if fecha is not None:
                return fecha
    return None


def construir_fecha(
    encontrada: re.Match[str], linea: Linea, siguiente: Linea | None
) -> Campo[datetime] | None:
    mes_texto = encontrada.group("mes")
    mes = MESES[mes_texto] if mes_texto in MESES else int(mes_texto)
    anio = int(encontrada.group("anio"))
    anio = anio + 2000 if anio < 100 else anio
    confianza = linea.confianza
    hora = HORA.search(linea.texto[encontrada.end() :]) or HORA.search(linea.texto)
    if hora is None and siguiente is not None:
        hora = HORA.search(siguiente.texto)
        confianza = min(confianza, siguiente.confianza) if hora else confianza
    horas, minutos = (int(hora.group("hora")), int(hora.group("minuto"))) if hora else (0, 0)
    if hora and hora.group("meridiano"):
        tarde = hora.group("meridiano").startswith("p")
        horas = horas % 12 + (12 if tarde else 0)
    try:
        return Campo(
            datetime(
                anio, mes, int(encontrada.group("dia")), horas, minutos, tzinfo=zona_horaria()
            ),
            confianza,
        )
    except ValueError:
        return None


def extraer_texto(lineas: list[Linea], entidad: Entidad, campo: str) -> tuple[str, float] | None:
    resultado = buscar(
        lineas, etiqueta_de(entidad, campo), VALORES[campo], cualquier_etiqueta(entidad)
    )
    if resultado is None:
        return None
    coincidencia, confianza = resultado
    return coincidencia.group("valor").strip(SEPARADOR), confianza


def extraer(lectura: LecturaOcr) -> DatosComprobante:
    lineas = [Linea(normalizar(linea.texto), linea.confianza) for linea in lectura.lineas]
    lineas = [linea for linea in lineas if linea.texto]
    entidad = detectar_entidad(lineas)
    monto, moneda = extraer_monto(lineas, entidad)
    operacion = extraer_texto(lineas, entidad, "operacion")
    empresa = extraer_texto(lineas, entidad, "empresa")
    codigo = extraer_texto(lineas, entidad, "codigo")
    numero = re.sub(r"\D", "", operacion[0]) if operacion else ""
    codigo_normal = re.sub(r"[\s-]", "", codigo[0]).upper() if codigo else ""
    return DatosComprobante(
        entidad=entidad,
        numero_operacion=Campo(numero, operacion[1]) if operacion and numero else None,
        monto=monto,
        moneda=moneda,
        fecha_pago=extraer_fecha(lineas, entidad),
        empresa=Campo(empresa[0].upper(), empresa[1]) if empresa else None,
        codigo=Campo(codigo_normal, codigo[1])
        if codigo and any(c.isdigit() for c in codigo_normal)
        else None,
    )
