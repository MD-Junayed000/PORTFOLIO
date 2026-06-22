import httpx
import logging
from html import escape
from typing import Optional, List

from config import settings

logger = logging.getLogger(__name__)


def is_email_configured() -> bool:
    """Check if Resend API key is configured."""
    return bool(settings.RESEND_API_KEY)


async def send_contact_notification(
    sender_name: str,
    sender_email: str,
    message: str,
    notification_emails_from_db: Optional[str] = None,
) -> bool:
    """Send email notification when a new contact message is received.

    Uses Resend's HTTPS API (port 443) which works on Render free tier
    where SMTP port 587 is blocked.

    Returns True if the email was sent successfully, False otherwise.
    """
    if not is_email_configured():
        logger.info("Resend API key not configured, skipping email notification")
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

    # Escape user input to prevent HTML injection
    safe_name = escape(sender_name)
    safe_email = escape(sender_email)
    safe_message = escape(message)

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

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://api.resend.com/emails",
                headers={"Authorization": f"Bearer {settings.RESEND_API_KEY}"},
                json={
                    "from": "Portfolio Contact <onboarding@resend.dev>",
                    "to": recipients,
                    "subject": f"New Contact Message from {sender_name}",
                    "html": html_content,
                },
                timeout=10.0,
            )

        if response.status_code == 200:
            logger.info(f"Contact notification email sent to {recipients}")
            return True
        else:
            logger.error(
                f"Resend API returned status {response.status_code}: "
                f"{response.text}"
            )
            return False

    except Exception as e:
        logger.error(f"Failed to send email notification via Resend: {e}")
        return False
