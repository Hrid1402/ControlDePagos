"""Banco de ejemplos de comprobantes por entidad (H24, TASK-86).

Cada ejemplo es la salida del OCR (líneas con su confianza) de un comprobante inventado: los
nombres de empresa son de servicios públicos conocidos, pero los códigos, montos, fechas y
números de operación no corresponden a ningún pago real. No se guardan comprobantes reales en el
repositorio; TASK-90 amplía este banco con ejemplos externos anonimizados.

esperado lleva los campos que debe extraer extraccion.extraer; None indica un campo que no debe
encontrar.
"""

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any

from app.core.tiempo import zona_horaria
from app.ocr.motor import LecturaOcr, Linea

LIMA = zona_horaria()


@dataclass(frozen=True)
class Ejemplo:
    nombre: str
    lineas: list[str]
    esperado: dict[str, Any]
    confianza: float = 0.98
    confianzas: dict[int, float] = field(default_factory=dict)

    def lectura(self) -> LecturaOcr:
        return LecturaOcr(
            [
                Linea(texto, self.confianzas.get(i, self.confianza))
                for i, texto in enumerate(self.lineas)
            ],
            paginas=1,
        )


def lima(anio: int, mes: int, dia: int, hora: int = 0, minuto: int = 0) -> datetime:
    return datetime(anio, mes, dia, hora, minuto, tzinfo=LIMA)


EJEMPLOS = [
    Ejemplo(
        "bcp_app",
        [
            "BCP",
            "Constancia de pago",
            "Pago de servicios",
            "Empresa",
            "HIDRANDINA",
            "Código de usuario",
            "12345678",
            "Monto pagado",
            "S/ 85.40",
            "Fecha y hora",
            "20 oct 2026 - 10:35 a.m.",
            "Número de operación",
            "00456789",
        ],
        {
            "entidad": "bcp",
            "empresa": "HIDRANDINA",
            "codigo": "12345678",
            "monto": Decimal("85.40"),
            "moneda": "PEN",
            "fecha_pago": lima(2026, 10, 20, 10, 35),
            "numero_operacion": "00456789",
        },
    ),
    Ejemplo(
        "interbank_app",
        [
            "Interbank",
            "¡Operación exitosa!",
            "Pago de servicio",
            "Empresa: SEDALIB",
            "Código de suministro: 4455-0021",
            "Monto: S/ 62.10",
            "Fecha: 18/10/2026 08:15",
            "Código de operación: 1029384756",
        ],
        {
            "entidad": "interbank",
            "empresa": "SEDALIB",
            "codigo": "44550021",
            "monto": Decimal("62.10"),
            "moneda": "PEN",
            "fecha_pago": lima(2026, 10, 18, 8, 15),
            "numero_operacion": "1029384756",
        },
    ),
    Ejemplo(
        "bbva_web",
        [
            "BBVA",
            "Pago realizado",
            "Empresa ENEL DISTRIBUCION",
            "Referencia 778899001",
            "Importe pagado S/ 1,234.50",
            "Fecha de operación 05/10/2026",
            "Hora 19:42",
            "Nº de operación 55667788",
        ],
        {
            "entidad": "bbva",
            "empresa": "ENEL DISTRIBUCION",
            "codigo": "778899001",
            "monto": Decimal("1234.50"),
            "moneda": "PEN",
            "fecha_pago": lima(2026, 10, 5, 19, 42),
            "numero_operacion": "55667788",
        },
    ),
    Ejemplo(
        "scotiabank_dolares",
        [
            "Scotiabank",
            "Constancia de Pago de Servicios",
            "Empresa: MOVISTAR FIJO",
            "Código de servicio: 0145 778 990",
            "Monto: US$ 45.50",
            "Fecha: 2026-10-12 14:03",
            "N° Operación: 99001122",
        ],
        {
            "entidad": "scotiabank",
            "empresa": "MOVISTAR FIJO",
            "codigo": "0145778990",
            "monto": Decimal("45.50"),
            "moneda": "USD",
            "fecha_pago": lima(2026, 10, 12, 14, 3),
            "numero_operacion": "99001122",
        },
    ),
    Ejemplo(
        "yape_servicio",
        [
            "¡Yapeaste!",
            "S/ 35",
            "Pago de servicio",
            "LUZ DEL SUR",
            "Código de suministro",
            "1122334",
            "Fecha 15 oct. 2026 | 09:20 p. m.",
            "Nro. de operación 03344556",
        ],
        {
            "entidad": "yape",
            "empresa": "LUZ DEL SUR",
            "codigo": "1122334",
            "monto": Decimal("35.00"),
            "moneda": "PEN",
            "fecha_pago": lima(2026, 10, 15, 21, 20),
            "numero_operacion": "03344556",
        },
    ),
    Ejemplo(
        "plin_servicio",
        [
            "plin",
            "Pago exitoso",
            "Empresa: CALIDDA",
            "Código de cliente: 33445566",
            "Monto S/ 78.90",
            "17/10/2026 11:05",
            "Número de operación: 77665544",
        ],
        {
            "entidad": "plin",
            "empresa": "CALIDDA",
            "codigo": "33445566",
            "monto": Decimal("78.90"),
            "moneda": "PEN",
            "fecha_pago": lima(2026, 10, 17, 11, 5),
            "numero_operacion": "77665544",
        },
    ),
    Ejemplo(
        "agente_bcp_voucher",
        [
            "AGENTE BCP",
            "PAGO DE SERVICIOS",
            "EMPRESA: HIDRANDINA",
            "COD.USUARIO: 87654321",
            "IMPORTE S/ 150.30",
            "FECHA: 19/10/26 HORA: 16:45",
            "NRO.OPER: 345678",
        ],
        {
            "entidad": "agente_bcp",
            "empresa": "HIDRANDINA",
            "codigo": "87654321",
            "monto": Decimal("150.30"),
            "moneda": "PEN",
            "fecha_pago": lima(2026, 10, 19, 16, 45),
            "numero_operacion": "345678",
        },
    ),
    Ejemplo(
        "kasnet_voucher",
        [
            "KASNET",
            "Comprobante de pago",
            "Empresa: EPSEL",
            "Código de pago: 20261019001",
            "Total: S/ 44.00",
            "Fecha: 19/10/2026",
            "Hora: 12:30",
            "Nro. Operación: 112233",
        ],
        {
            "entidad": "kasnet",
            "empresa": "EPSEL",
            "codigo": "20261019001",
            "monto": Decimal("44.00"),
            "moneda": "PEN",
            "fecha_pago": lima(2026, 10, 19, 12, 30),
            "numero_operacion": "112233",
        },
    ),
    Ejemplo(
        "bcp_sin_codigo",
        [
            "BCP",
            "Constancia de pago",
            "Empresa: HIDRANDINA",
            "Monto pagado: S/ 85.40",
            "Fecha: 20/10/2026 10:35",
            "Número de operación: 00456790",
        ],
        {"entidad": "bcp", "codigo": None, "faltantes": ["codigo"]},
    ),
    Ejemplo(
        "entidad_desconocida",
        [
            "Caja Municipal",
            "Pago de servicios",
            "Empresa: HIDRANDINA",
            "Código de usuario: 12345678",
            "Monto: S/ 85.40",
            "Fecha: 20/10/2026",
        ],
        {"entidad": "otra", "empresa": "HIDRANDINA", "monto": Decimal("85.40")},
    ),
    Ejemplo(
        "dos_importes_sin_etiqueta",
        ["BCP", "Pago de servicios", "S/ 10.00", "S/ 1.00", "20/10/2026"],
        {"entidad": "bcp", "monto": None, "moneda": "PEN", "fecha_pago": lima(2026, 10, 20)},
    ),
]
