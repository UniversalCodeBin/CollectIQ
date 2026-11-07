"""ClamAV scanning (fails closed) and SMTP delivery, against local fake servers only."""

import socket
import struct
import threading
from collections.abc import Iterator
from contextlib import contextmanager

import pytest
from django.conf import settings

from collectiq.platform import email as email_port
from collectiq.platform import scan
from collectiq.platform.errors import ProblemError


@contextmanager
def fake_clamd(reply: bytes) -> Iterator[tuple[int, list[bytes]]]:
    """Speaks just enough of the clamd INSTREAM protocol. Yields (port, received payloads)."""
    received: list[bytes] = []
    server = socket.socket()
    server.bind(("127.0.0.1", 0))
    server.listen(1)

    def serve() -> None:
        conn, _ = server.accept()
        with conn:
            buf = b""
            while len(buf) < 10:
                buf += conn.recv(10 - len(buf))
            assert buf == b"zINSTREAM\0"
            data = b""
            while True:
                head = b""
                while len(head) < 4:
                    head += conn.recv(4 - len(head))
                (size,) = struct.unpack("!I", head)
                if size == 0:
                    break
                chunk = b""
                while len(chunk) < size:
                    chunk += conn.recv(size - len(chunk))
                data += chunk
            received.append(data)
            conn.sendall(reply)

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    try:
        yield server.getsockname()[1], received
    finally:
        server.close()
        thread.join(timeout=2)


def clam(port: int) -> scan.ClamAVScanner:
    return scan.ClamAVScanner("127.0.0.1", port, timeout=2)


def test_a_clean_file_is_clean_and_the_bytes_reach_the_scanner() -> None:
    with fake_clamd(b"stream: OK\0") as (port, received):
        assert clam(port).scan(b"hello " * 50_000) == "CLEAN"
    assert received == [b"hello " * 50_000]


def test_a_detection_is_quarantined() -> None:
    with fake_clamd(b"stream: Eicar-Test-Signature FOUND\0") as (port, _):
        assert clam(port).scan(b"x") == "QUARANTINED"


def test_a_scanner_error_reply_fails_closed() -> None:
    with (
        fake_clamd(b"INSTREAM size limit exceeded. ERROR\0") as (port, _),
        pytest.raises(ProblemError) as err,
    ):
        clam(port).scan(b"x")
    assert err.value.status == 503 and err.value.code == "SCAN_UNAVAILABLE"


def test_an_unreachable_scanner_fails_closed() -> None:
    probe = socket.socket()
    probe.bind(("127.0.0.1", 0))
    port = probe.getsockname()[1]
    probe.close()
    with pytest.raises(ProblemError) as err:
        clam(port).scan(b"x")
    assert err.value.status == 503


def test_the_scanner_is_chosen_by_setting(monkeypatch: pytest.MonkeyPatch) -> None:
    assert isinstance(scan.get_scanner(), scan.NoopScanner)
    monkeypatch.setattr(settings, "SCANNER_KIND", "clamav", raising=False)
    assert isinstance(scan.get_scanner(), scan.ClamAVScanner)
    monkeypatch.setattr(settings, "SCANNER_KIND", "bogus", raising=False)
    with pytest.raises(RuntimeError):
        scan.get_scanner()


def test_smtp_delivery_sends_the_message(monkeypatch: pytest.MonkeyPatch) -> None:
    sent: list[tuple[str, str, str, str]] = []

    class FakeSMTP:
        def __init__(self, host: str, port: int, timeout: float) -> None:
            sent.append(("connect", host, str(port), ""))

        def __enter__(self) -> "FakeSMTP":
            return self

        def __exit__(self, *_: object) -> None:
            return None

        def starttls(self, **_: object) -> None:
            sent.append(("starttls", "", "", ""))

        def login(self, user: str, password: str) -> None:
            sent.append(("login", user, "", ""))

        def send_message(self, msg: object) -> None:
            sent.append(("send", str(msg["To"]), str(msg["From"]), str(msg["Subject"])))  # type: ignore[index]

    monkeypatch.setattr(email_port.smtplib, "SMTP", FakeSMTP)
    for name, value in {
        "EMAIL_BACKEND_KIND": "smtp",
        "SMTP_HOST": "smtp.example.test",
        "SMTP_PORT": 587,
        "SMTP_USER": "mailer",
        "SMTP_PASSWORD": "placeholder",  # pragma: allowlist secret
        "SMTP_FROM": "noreply@example.test",
        "SMTP_STARTTLS": True,
    }.items():
        monkeypatch.setattr(settings, name, value, raising=False)
    email_port.send_email("a@example.test", "Hello", "Body")
    assert [s[0] for s in sent] == ["connect", "starttls", "login", "send"]
    assert sent[-1] == ("send", "a@example.test", "noreply@example.test", "Hello")


def test_smtp_refuses_header_injection(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "EMAIL_BACKEND_KIND", "smtp", raising=False)
    with pytest.raises(ValueError):
        email_port.send_email("a@example.test\nBcc: x@example.test", "Hi", "Body")
    with pytest.raises(ValueError):
        email_port.send_email("a@example.test", "Hi\nBcc: x@example.test", "Body")
