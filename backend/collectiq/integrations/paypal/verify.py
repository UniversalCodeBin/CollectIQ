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


class MerchantChecker(Protocol):
    def confirm(self, merchant_id: str) -> bool:
        """True only if PayPal confirms the merchant id belongs to the account being connected."""


class UnconfiguredMerchantChecker:
    def confirm(self, merchant_id: str) -> bool:
        return False


class FakeMerchantChecker:
    def confirm(self, merchant_id: str) -> bool:
        return merchant_id.startswith("FAKE")


_checker: MerchantChecker | None = None


def set_merchant_checker(checker: MerchantChecker | None) -> None:
    global _checker
    _checker = checker


def get_merchant_checker() -> MerchantChecker:
    return _checker or UnconfiguredMerchantChecker()
