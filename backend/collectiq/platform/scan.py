"""The malware-scan port. `SCANNER_KIND=none` records uploads as not scanned (local default).
`clamav` streams each file to a clamd daemon and fails closed: no answer means the upload is refused."""

import socket
import struct
from typing import Literal, Protocol

from django.conf import settings

from .errors import ProblemError

ScanStatus = Literal["NOT_SCANNED", "CLEAN", "QUARANTINED"]
_CHUNK = 64 * 1024


class ScannerPort(Protocol):
    def scan(self, data: bytes) -> ScanStatus: ...


class NoopScanner:
    def scan(self, data: bytes) -> ScanStatus:
        return "NOT_SCANNED"


def _unavailable() -> ProblemError:
    return ProblemError(
        "SCAN_UNAVAILABLE",
        503,
        "The file could not be checked for malware, so it was not accepted. Try again later.",
    )


class ClamAVScanner:
    def __init__(self, host: str, port: int, timeout: float = 30.0) -> None:
        self.host, self.port, self.timeout = host, port, timeout

    def scan(self, data: bytes) -> ScanStatus:
        try:
            with socket.create_connection((self.host, self.port), timeout=self.timeout) as conn:
                conn.sendall(b"zINSTREAM\0")
                for start in range(0, len(data), _CHUNK):
                    chunk = data[start : start + _CHUNK]
                    conn.sendall(struct.pack("!I", len(chunk)) + chunk)
                conn.sendall(struct.pack("!I", 0))
                reply = b""
                while not reply.endswith(b"\0") and len(reply) < 4096:
                    part = conn.recv(1024)
                    if not part:
                        break
                    reply += part
        except OSError as exc:
            raise _unavailable() from exc
        text = reply.rstrip(b"\0\n").decode("ascii", "replace")
        if text.endswith("OK"):
            return "CLEAN"
        if text.endswith("FOUND"):
            return "QUARANTINED"
        raise _unavailable()


def get_scanner() -> ScannerPort:
    kind = getattr(settings, "SCANNER_KIND", "none")
    if kind == "none":
        return NoopScanner()
    if kind == "clamav":
        return ClamAVScanner(settings.CLAMAV_HOST, settings.CLAMAV_PORT, settings.CLAMAV_TIMEOUT)
    raise RuntimeError(f"unknown SCANNER_KIND: {kind}")
