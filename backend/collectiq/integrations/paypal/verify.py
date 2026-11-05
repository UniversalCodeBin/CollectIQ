"""The PayPal webhook signature port. Nothing here has been verified against PayPal."""

from collections.abc import Mapping
from typing import Protocol


class WebhookVerifier(Protocol):
    def verify(self, headers: Mapping[str, str], body: bytes) -> bool: ...


class UnconfiguredVerifier:
    """Without a live verifier every event is refused."""

    def verify(self, headers: Mapping[str, str], body: bytes) -> bool:
        return False


class FakeVerifier:
    def verify(self, headers: Mapping[str, str], body: bytes) -> bool:
        return headers.get("X-Fake-Signature") == "valid"


_verifier: WebhookVerifier | None = None


def set_verifier(verifier: WebhookVerifier | None) -> None:
    global _verifier
    _verifier = verifier


def get_verifier() -> WebhookVerifier:
    return _verifier or UnconfiguredVerifier()
