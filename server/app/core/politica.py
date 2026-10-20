"""Política de privacidad vigente (H02 CA10).

Contenido según el deber de información del artículo 18 de la Ley 29733 y el artículo 6.1 de su
reglamento (DS 016-2024-JUS): responsable y contacto, datos tratados, finalidades, decisiones
automatizadas, destinatarios y transferencias, carácter obligatorio y consecuencias, plazo de
conservación, seguridad, derechos y cómo ejercerlos.

Es la única fuente de la política: el cliente la pide por la API y la aceptación solo vale para la
versión vigente. Cambiar el texto obliga a subir VERSION, y cada usuario debe aceptarla de nuevo.
Los datos del responsable salen de la configuración de cada instalación.
"""

from dataclasses import dataclass
from datetime import date

from app.core.config import settings

VERSION = "2026-10"
VIGENTE_DESDE = date(2026, 10, 20)


@dataclass(frozen=True)
class Seccion:
    titulo: str
    parrafos: tuple[str, ...]


def secciones() -> tuple[Seccion, ...]:
    # Sin correo configurado la frase no puede inventar uno: remite a los canales del responsable.
    contacto = (
        f"escríbenos a {settings.politica_correo}"
        if settings.politica_correo
        else "usa los canales de contacto que publique el responsable"
    )
    domicilio = (
        f", con domicilio en {settings.politica_domicilio}" if settings.politica_domicilio else ""
    )
    return (
        Seccion(
            "Quién trata tus datos",
            (
                f"El responsable del tratamiento es {settings.politica_responsable}{domicilio}. "
                f"Para cualquier consulta sobre tus datos, {contacto}.",
                "Tus datos forman parte del banco de datos de usuarios y pagos de Control de "
                "Pagos, el sistema con el que un gerente delega en su asistente el pago de sus "
                "gastos.",
            ),
        ),
        Seccion(
            "Qué datos tratamos",
            (
                "De identificación y contacto: nombres, apellidos, tipo y número de documento, "
                "correo y celular.",
                "De acceso: tu usuario, tu contraseña guardada cifrada, tus ingresos y, en el "
                "historial de acciones, el dispositivo y la dirección IP desde donde actuaste.",
                "De los pagos que se registran: servicios, deudas, montos, órdenes de pago, "
                "recibos y comprobantes, que pueden incluir números de operación y cuentas.",
                "No pedimos datos sensibles.",
            ),
        ),
        Seccion(
            "Para qué los usamos",
            (
                "Para identificarte y darte acceso según tu rol, y para ayudarte a recuperarlo "
                "por correo si olvidas tu contraseña.",
                "Para registrar, ordenar, pagar y verificar los gastos que el gerente delega en "
                "su asistente, y avisarte dentro de la aplicación de lo que requiere tu atención.",
                "Para dejar constancia de quién hizo cada acción y cuándo, y proteger la cuenta "
                "frente a accesos indebidos.",
                "No usamos tus datos con fines publicitarios ni los vendemos.",
            ),
        ),
        Seccion(
            "Decisiones automatizadas",
            (
                "Los comprobantes que subes se leen de forma automática y se comparan con la "
                "deuda (monto, fecha, empresa y número de operación) para validarlos. Si algo no "
                "coincide o no se puede leer, el comprobante pasa a revisión del gerente: una "
                "persona decide. No elaboramos perfiles sobre ti.",
            ),
        ),
        Seccion(
            "Quién más los ve",
            (
                "Tu gerente y la asistente activa de su cuenta, cada uno solo en lo que su rol "
                "permite.",
                "Los proveedores que nos dan alojamiento, almacenamiento de archivos y envío de "
                "correos, que solo tratan los datos por encargo nuestro y bajo nuestras "
                "instrucciones.",
                "Antes de transferir tus datos a otro responsable o fuera del Perú te lo "
                "informaremos y, cuando la ley lo exija, te pediremos tu consentimiento.",
            ),
        ),
        Seccion(
            "Qué datos son obligatorios",
            (
                "Nombres, apellidos, correo y celular son obligatorios: sin ellos no podemos "
                "identificarte ni ayudarte a recuperar el acceso. El documento es opcional.",
            ),
        ),
        Seccion(
            "Cuánto tiempo los conservamos",
            (
                "Mientras tu cuenta esté vigente. Si se elimina, dejas de tener acceso, pero tu "
                "nombre se conserva en el historial de acciones para dejar constancia de lo que "
                "hiciste.",
                "Los registros de pagos y comprobantes se conservan mientras el gerente mantenga "
                "su cuenta y, después, solo por el plazo que exijan las normas tributarias y "
                "contables. Vencido ese plazo, se eliminan o se anonimizan.",
            ),
        ),
        Seccion(
            "Cómo los protegemos",
            (
                "Guardamos las contraseñas cifradas, damos acceso solo según el rol, cerramos "
                "las sesiones inactivas, guardamos los archivos en un almacenamiento privado con "
                "enlaces temporales y registramos cada acción en un historial que no se edita.",
            ),
        ),
        Seccion(
            "Tus derechos",
            (
                "Puedes pedir información sobre el tratamiento de tus datos, acceder a ellos, "
                "rectificarlos, cancelarlos, oponerte a su tratamiento, pedir su portabilidad y "
                "revocar tu consentimiento. Muchos datos los corriges tú mismo en Mi cuenta.",
                f"Para ejercer estos derechos, {contacto}. Respondemos en los plazos "
                "del reglamento: 8 días hábiles para el derecho de información, 20 para el de "
                "acceso y 10 para los de rectificación, cancelación y oposición.",
                "Si no atendemos tu pedido, puedes presentar una reclamación ante la Autoridad "
                "Nacional de Protección de Datos Personales del Ministerio de Justicia y Derechos "
                "Humanos.",
            ),
        ),
        Seccion(
            "Cambios en esta política",
            (
                "Si cambiamos esta política, publicaremos una versión nueva y te pediremos "
                "aceptarla al ingresar. Se rige por la Ley 29733, Ley de Protección de Datos "
                "Personales, y su reglamento, aprobado por el Decreto Supremo 016-2024-JUS.",
            ),
        ),
    )
