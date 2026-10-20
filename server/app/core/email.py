import logging
import smtplib
from email.message import EmailMessage

from app.core.config import settings

logger = logging.getLogger(__name__)


def enviar_correo(destinatario: str, asunto: str, contenido_texto: str) -> bool:
    """Envía un correo mediante el servidor SMTP configurado. Si el servidor no responde,
    registra una advertencia y retorna False para no interrumpir el flujo."""
    try:
        mensaje = EmailMessage()
        mensaje["Subject"] = asunto
        mensaje["From"] = settings.smtp_from
        mensaje["To"] = destinatario
        mensaje.set_content(contenido_texto)

        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as servidor:
            if settings.smtp_tls:
                servidor.starttls()
            if settings.smtp_user and settings.smtp_password:
                servidor.login(settings.smtp_user, settings.smtp_password)
            servidor.send_message(mensaje)
        return True
    except Exception as exc:
        # Ni el destinatario ni el texto del error: pueden incluir la dirección.
        logger.warning(
            "No se pudo enviar el correo (host=%s, port=%s): %s",
            settings.smtp_host,
            settings.smtp_port,
            type(exc).__name__,
        )
        return False
