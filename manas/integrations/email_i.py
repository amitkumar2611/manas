"""Email adapter (SMTP, stdlib): sending email is APPROVAL, always."""
import smtplib
from email.message import EmailMessage

from manas.kernel.config import settings
from manas.kernel.errors import ProviderError
from manas.kernel.registry import tools


@tools.register("email_send")
class EmailSend:
    risk_level = "APPROVAL"
    approval_reason = "sends an email from your account"

    async def __call__(self, to: str, subject: str, body: str) -> dict:
        if not (settings.smtp_host and settings.smtp_from):
            raise ProviderError("set MANAS_SMTP_HOST / _SMTP_FROM (and creds)")
        msg = EmailMessage()
        msg["From"], msg["To"], msg["Subject"] = settings.smtp_from, to, subject
        msg.set_content(body)
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as s:
            s.starttls()
            if settings.smtp_user:
                s.login(settings.smtp_user, settings.smtp_pass)
            s.send_message(msg)
        return {"sent": True, "to": to}
