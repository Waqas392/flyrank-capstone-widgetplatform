"""Confirmation email. Console log by default; SMTP (e.g. Mailpit) when SMTP_HOST is set."""
from __future__ import annotations

import logging
import smtplib
from email.message import EmailMessage

from ..config import Settings
from .faults import Faults

log = logging.getLogger("notify")


def send_email(settings: Settings, faults: Faults, to: str, subject: str, body: str) -> None:
    """Synchronous; runs inside the job worker, never on the request path."""
    if faults.email_fail:
        raise RuntimeError("email delivery failed (fault injected)")
    if not settings.smtp_host:
        log.info("EMAIL (console) to=%s subject=%r", to, subject)
        return
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = settings.mail_from, to, subject
    msg.set_content(body)
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as s:
        s.send_message(msg)
