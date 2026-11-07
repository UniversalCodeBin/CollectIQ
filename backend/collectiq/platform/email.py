"""Outgoing mail through a port. `memory` and `file` stay local; `smtp` uses the configured server."""
import os
import smtplib
import uuid
from dataclasses import dataclass
from email.message import EmailMessage

from django.conf import settings


@dataclass(frozen=True, slots=True)
class Email:
    to: str
    subject: str
    body: str


memory_outbox: list[Email] = []


def _write_file(message: Email) -> None:
    directory = settings.EMAIL_FILE_PATH
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{uuid.uuid4()}.eml"
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(f"To: {message.to}\nSubject: {message.subject}\n\n{message.body}\n")


def _send_smtp(message: Email) -> None:
    for value in (message.to, message.subject):
        if "\r" in value or "\n" in value:
            raise ValueError("line breaks are not allowed in an address or subject")
    mime = EmailMessage()
    mime["To"] = message.to
    mime["From"] = settings.SMTP_FROM
    mime["Subject"] = message.subject
    mime.set_content(message.body)
    with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=20) as server:
        if settings.SMTP_STARTTLS:
            server.starttls()
        if settings.SMTP_USER:
            server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
        server.send_message(mime)


def _deliver(message: Email) -> None:
    kind = settings.EMAIL_BACKEND_KIND
    if kind == "memory":
        memory_outbox.append(message)
    elif kind == "file":
        _write_file(message)
    elif kind == "smtp":
        _send_smtp(message)
    else:
        raise RuntimeError(f"unknown EMAIL_BACKEND_KIND: {kind}")


def send_email(to: str, subject: str, body: str) -> None:
    _deliver(Email(to, subject, body))
