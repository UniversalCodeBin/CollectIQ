"""Outgoing mail through a local port. Only local backends exist: nothing reaches a real mailbox."""
import os
import uuid
from dataclasses import dataclass

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


def _deliver(message: Email) -> None:
    kind = settings.EMAIL_BACKEND_KIND
    if kind == "memory":
        memory_outbox.append(message)
    elif kind == "file":
        _write_file(message)
    else:
        raise RuntimeError(f"unknown EMAIL_BACKEND_KIND: {kind}")


def send_email(to: str, subject: str, body: str) -> None:
    _deliver(Email(to, subject, body))
