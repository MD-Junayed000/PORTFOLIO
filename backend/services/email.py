import asyncio
import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from html import escape
from typing import Optional, List

from config import settings

logger = logging.getLogger(__name__)


def is_email_configured() -> bool:
    """Check if SMTP settings are configured."""
    return bool(
        settings.SMTP_HOST
        and settings.SMTP_USER
        and settings.SMTP_PASSWORD
    )


def _send_email_sync(
    sender_name: str,
    sender_email: str,
    message: str,
    recipients: List[str],
) -> bool:
    """Synchronous email send - meant to be called via asyncio.to_thread.

    Returns True if the email was sent successfully, False otherwise.
    """
    if not recipients:
        return False

    try:
        # Escape user input to prevent HTML injection
        safe_name = escape(sender_name)
        safe_email = escape(sender_email)
        safe_message = escape(message)

        for recipient in recipients:
            recipient = recipient.strip()
            if not recipient:
                continue

            msg = MIMEMultipart("alternative")
            msg["Subject"] = f"New Contact Message from {safe_name}"
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
                        <td style="padding: 8px;">{safe_name}</td>
                    </tr>
                    <tr>
                        <td style="padding: 8px; font-weight: bold; color: #555;">Email:</td>
                        <td style="padding: 8px;"><a href="mailto:{safe_email}">{safe_email}</a></td>
                    </tr>
                </table>
                <div style="margin-top: 20px; padding: 15px; background-color: #f5f5f5; border-radius: 8px;">
                    <p style="font-weight: bold; color: #555; margin-bottom: 8px;">Message:</p>
                    <p style="white-space: pre-wrap; color: #333;">{safe_message}</p>
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


async def send_contact_notification(
    sender_name: str,
    sender_email: str,
    message: str,
    notification_emails_from_db: Optional[str] = None,
) -> bool:
    """Send email notification when a new contact message is received.

    Runs the blocking SMTP operation in a thread to avoid blocking the event loop.
    Uses notification_emails from the database if available, otherwise falls back
    to the NOTIFICATION_EMAIL environment variable.

    Returns True if the email was sent successfully, False otherwise.
    """
    if not is_email_configured():
        logger.info("SMTP not configured, skipping email notification")
        return False

    # Build recipient list: prefer DB-configured emails, fall back to env var
    recipients: List[str] = []
    if notification_emails_from_db:
        # Parse comma-separated email list from database
        recipients = [
            email.strip()
            for email in notification_emails_from_db.split(",")
            if email.strip()
        ]

    # Fall back to env var if no DB recipients configured
    if not recipients and settings.NOTIFICATION_EMAIL:
        recipients = [settings.NOTIFICATION_EMAIL]

    if not recipients:
        logger.info("No notification recipients configured, skipping email")
        return False

    # Run blocking SMTP in a thread to avoid blocking the async event loop
    return await asyncio.to_thread(
        _send_email_sync,
        sender_name,
        sender_email,
        message,
        recipients,
    )
