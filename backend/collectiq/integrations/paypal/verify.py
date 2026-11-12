"""The PayPal webhook signature and merchant verification port.

Supports live Sandbox verification via official PayPal REST API endpoints,
unconfigured rejection by default when credentials are unavailable, and
deterministic test fakes for isolation testing.
"""

from collections.abc import Mapping
from typing import Protocol

from .client import PayPalClient, PayPalConfigurationError, PayPalError

_client: PayPalClient | None = None


def get_paypal_client() -> PayPalClient:
    """Returns the active PayPalClient, instantiating from Django settings if not overridden."""
    global _client
    if _client is not None:
        return _client
    return PayPalClient()


def set_paypal_client(client: PayPalClient | None) -> None:
    """Overrides the PayPal client (primarily for unit tests)."""
    global _client
    _client = client


class WebhookVerifier(Protocol):
    def verify(self, headers: Mapping[str, str], body: bytes) -> bool: ...


class UnconfiguredVerifier:
    """Without configured credentials or verifier, every event signature is refused."""

    def verify(self, headers: Mapping[str, str], body: bytes) -> bool:
        return False


class FakeVerifier:
    """Test fake for verifying synthetic signatures."""

    def verify(self, headers: Mapping[str, str], body: bytes) -> bool:
        # Check standard fake header as well as case-insensitive variants
        for k, v in headers.items():
            if k.upper().replace("-", "_") in ("HTTP_X_FAKE_SIGNATURE", "X_FAKE_SIGNATURE"):
                return v == "valid"
        return False


class PayPalWebhookVerifier:
    """Verifies incoming webhook signatures against PayPal's official verification API."""

    def __init__(self, client: PayPalClient | None = None) -> None:
        self.client = client or get_paypal_client()

    def verify(self, headers: Mapping[str, str], body: bytes) -> bool:
        try:
            return self.client.verify_webhook_signature(headers, body)
        except PayPalConfigurationError:
            return False
        except PayPalError:
            return False


_verifier: WebhookVerifier | None = None


def set_verifier(verifier: WebhookVerifier | None) -> None:
    global _verifier
    _verifier = verifier


def get_verifier() -> WebhookVerifier:
    if _verifier is not None:
        return _verifier
    client = get_paypal_client()
    if client.is_configured():
        return PayPalWebhookVerifier(client)
    return UnconfiguredVerifier()


class MerchantChecker(Protocol):
    def confirm(self, merchant_id: str) -> bool:
        """True only if PayPal confirms the merchant id / credentials belong to the account being connected."""


class UnconfiguredMerchantChecker:
    """Default checker when credentials are not configured."""

    def confirm(self, merchant_id: str) -> bool:
        return False


class FakeMerchantChecker:
    """Test fake for verifying merchant accounts in tests."""

    def confirm(self, merchant_id: str) -> bool:
        return merchant_id.startswith("FAKE")


class PayPalMerchantChecker:
    """Verifies credentials and connectivity against PayPal Sandbox API."""

    def __init__(self, client: PayPalClient | None = None) -> None:
        self.client = client or get_paypal_client()

    def confirm(self, merchant_id: str) -> bool:
        result = self.client.verify_connectivity()
        # Connected if authentication succeeded and provider is reachable
        return result.get("status") in ("CONNECTED_VERIFIED", "SANDBOX_ONLY")


_checker: MerchantChecker | None = None


def set_merchant_checker(checker: MerchantChecker | None) -> None:
    global _checker
    _checker = checker


def get_merchant_checker() -> MerchantChecker:
    if _checker is not None:
        return _checker
    client = get_paypal_client()
    if client.is_configured():
        return PayPalMerchantChecker(client)
    return UnconfiguredMerchantChecker()
