"""Sending email: for now, the links to set a new password.

Through SMTP when VERITAS_SMTP_HOST is set (port 587 upgrades with STARTTLS, 465 is TLS from
the start). With VERITAS_MAIL_ECHO the message goes to the log instead, so a developer can
follow its link; production refuses that setting. With neither, nothing can be sent and the
caller is told so.
"""

from __future__ import annotations

import logging
import smtplib
import ssl
from email.message import EmailMessage

from veritas.settings import Settings

logger = logging.getLogger("veritas.mail")

TIMEOUT_SECONDS = 15


class MailNotSent(Exception):
    pass


def send(settings: Settings, to: str, subject: str, body: str) -> None:
    if settings.mail_echo:
        logger.info("Mail to %s: %s\n%s", to, subject, body)
        return
    if not settings.smtp_host:
        raise MailNotSent("no SMTP server is set (VERITAS_SMTP_HOST)")
    message = EmailMessage()
    message["From"] = settings.mail_from
    message["To"] = to
    message["Subject"] = subject
    message.set_content(body)
    context = ssl.create_default_context()
    try:
        if settings.smtp_port == 465:
            server: smtplib.SMTP = smtplib.SMTP_SSL(
                settings.smtp_host, settings.smtp_port, timeout=TIMEOUT_SECONDS, context=context
            )
        else:
            server = smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=TIMEOUT_SECONDS)
        with server:
            if settings.smtp_port != 465 and settings.smtp_starttls:
                server.starttls(context=context)
            if settings.smtp_username:
                password = (
                    settings.smtp_password.get_secret_value() if settings.smtp_password else ""
                )
                server.login(settings.smtp_username, password)
            server.send_message(message)
    except (OSError, smtplib.SMTPException) as error:
        raise MailNotSent(str(error)) from error
