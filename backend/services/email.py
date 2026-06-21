import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional

from config import settings

logger = logging.getLogger(__name__)


def is_email_configured() -> bool:
    """Check if SMTP settings are configured."""
    return bool(
        settings.SMTP_HOST
        and settings.SMTP_USER
        and settings.SMTP_PASSWORD
        and settings.NOTIFICATION_EMAIL
    )


def send_contact_notification(
    sender_name: str,
    sender_email: str,
    message: str,
    recipient_override: Optional[str] = None,
) -> bool:
    """Send email notification when a new contact message is received.

    Returns True if the email was sent successfully, False otherwise.
    """
    if not is_email_configured():
        logger.info("SMTP not configured, skipping email notification")
        return False

    recipient = recipient_override or settings.NOTIFICATION_EMAIL
    if not recipient:
        return False

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"New Contact Message from {sender_name}"
        msg["From"] = settings.SMTP_USER
        msg["To"] = recipient

        text_content = (
            f"New contact message received:\n\n"
            f"From: {sender_name}\n"
            f"Email: {sender_email}\n\n"
            f"Message:\n{message}\n"
        )

        html_content = f"""
        <html>
        <body style="font-family: Arial, sans-serif; padding: 20px;">
            <h2 style="color: #333;">New Contact Message</h2>
            <table style="border-collapse: collapse; width: 100%; max-width: 600px;">
                <tr>
                    <td style="padding: 8px; font-weight: bold; color: #555;">From:</td>
                    <td style="padding: 8px;">{sender_name}</td>
                </tr>
                <tr>
                    <td style="padding: 8px; font-weight: bold; color: #555;">Email:</td>
                    <td style="padding: 8px;"><a href="mailto:{sender_email}">{sender_email}</a></td>
                </tr>
            </table>
            <div style="margin-top: 20px; padding: 15px; background-color: #f5f5f5; border-radius: 8px;">
                <p style="font-weight: bold; color: #555; margin-bottom: 8px;">Message:</p>
                <p style="white-space: pre-wrap; color: #333;">{message}</p>
            </div>
        </body>
        </html>
        """

        msg.attach(MIMEText(text_content, "plain"))
        msg.attach(MIMEText(html_content, "html"))

        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as server:
            server.starttls()
            server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            server.send_message(msg)

        logger.info(f"Contact notification email sent to {recipient}")
        return True

    except Exception as e:
        logger.error(f"Failed to send email notification: {e}")
        return False
