"""The malware-scan port. No scanner is decided yet (OD-14), so uploads are recorded as not scanned."""

from typing import Literal, Protocol

ScanStatus = Literal["NOT_SCANNED", "CLEAN", "QUARANTINED"]


class ScannerPort(Protocol):
    def scan(self, data: bytes) -> ScanStatus: ...


class NoopScanner:
    def scan(self, data: bytes) -> ScanStatus:
        return "NOT_SCANNED"


def get_scanner() -> ScannerPort:
    return NoopScanner()
