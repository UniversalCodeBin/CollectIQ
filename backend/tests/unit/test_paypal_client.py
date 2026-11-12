"""Unit tests for PayPal REST API client, OAuth token caching, and webhook signature verification."""

import json
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError, URLError

import pytest

from collectiq.integrations.paypal.client import (
    PayPalAuthenticationError,
    PayPalClient,
    PayPalConfigurationError,
    PayPalMissingCredentialsError,
    PayPalPermissionError,
    PayPalProviderUnavailableError,
    PayPalRateLimitError,
    redact_sensitive,
)


def test_redact_sensitive() -> None:
    data = {
        "client_id": "public-id",
        "client_secret": "super-secret-key",
        "nested": {"access_token": "token-123", "normal": "hello"},
        "transmission_sig": "sig-abc",
    }
    redacted = redact_sensitive(data)
    assert redacted["client_id"] == "public-id"
    assert redacted["client_secret"] == "***REDACTED***"
    assert redacted["nested"]["access_token"] == "***REDACTED***"
    assert redacted["nested"]["normal"] == "hello"
    assert redacted["transmission_sig"] == "***REDACTED***"


def test_client_is_configured() -> None:
    unconfigured = PayPalClient(client_id="", client_secret="")
    assert not unconfigured.is_configured()

    configured = PayPalClient(client_id="ID-123", client_secret="SECRET-456")
    assert configured.is_configured()


def test_missing_credentials_raises() -> None:
    client = PayPalClient(client_id="", client_secret="")
    with pytest.raises(PayPalMissingCredentialsError):
        client.get_access_token()


def test_oauth_token_acquired_and_cached() -> None:
    client = PayPalClient(
        client_id="TEST-CLIENT-ID",
        client_secret="TEST-CLIENT-SECRET",
        base_url="https://api-m.sandbox.paypal.com",
    )

    mock_response = MagicMock()
    mock_response.status = 200
    mock_response.read.return_value = json.dumps({
        "access_token": "A21AA-test-access-token",
        "token_type": "Bearer",
        "app_id": "APP-TEST",
        "expires_in": 3600,
    }).encode("utf-8")

    with patch("urllib.request.urlopen", return_value=mock_response) as mock_urlopen:
        mock_response.__enter__.return_value = mock_response
        token1 = client.get_access_token()
        assert token1 == "A21AA-test-access-token"
        assert mock_urlopen.call_count == 1

        # Second call should reuse cached token
        token2 = client.get_access_token()
        assert token2 == "A21AA-test-access-token"
        assert mock_urlopen.call_count == 1

        # Force refresh should call endpoint again
        token3 = client.get_access_token(force_refresh=True)
        assert token3 == "A21AA-test-access-token"
        assert mock_urlopen.call_count == 2


def test_oauth_authentication_failure_401() -> None:
    client = PayPalClient(
        client_id="INVALID-ID",
        client_secret="INVALID-SECRET",
    )

    error_response = MagicMock()
    error_response.code = 401
    error_response.read.return_value = json.dumps({
        "error": "invalid_client",
        "error_description": "Client Authentication failed",
    }).encode("utf-8")
    http_error = HTTPError("url", 401, "Unauthorized", {}, error_response)

    with patch("urllib.request.urlopen", side_effect=http_error):
        with pytest.raises(PayPalAuthenticationError) as exc_info:
            client.get_access_token()
        assert "Authentication failed" in str(exc_info.value)


def test_oauth_permission_denied_403() -> None:
    client = PayPalClient(client_id="ID", client_secret="SECRET", max_retries=1)

    error_response = MagicMock()
    error_response.code = 403
    error_response.read.return_value = json.dumps({"message": "Forbidden access"}).encode("utf-8")
    http_error = HTTPError("url", 403, "Forbidden", {}, error_response)

    with patch("urllib.request.urlopen", side_effect=http_error):
        with pytest.raises(PayPalPermissionError):
            client.get_access_token()


def test_oauth_rate_limit_429() -> None:
    client = PayPalClient(client_id="ID", client_secret="SECRET", max_retries=1)

    error_response = MagicMock()
    error_response.code = 429
    error_response.read.return_value = json.dumps({"message": "Rate limited"}).encode("utf-8")
    http_error = HTTPError("url", 429, "Too Many Requests", {}, error_response)

    with patch("urllib.request.urlopen", side_effect=http_error):
        with pytest.raises(PayPalRateLimitError):
            client.get_access_token()


def test_oauth_server_error_5xx_retries_and_raises_unavailable() -> None:
    client = PayPalClient(client_id="ID", client_secret="SECRET", max_retries=2)

    error_response = MagicMock()
    error_response.code = 503
    error_response.read.return_value = b"Service Unavailable"
    http_error = HTTPError("url", 503, "Service Unavailable", {}, error_response)

    with patch("urllib.request.urlopen", side_effect=http_error) as mock_urlopen:
        with patch("time.sleep"):
            with pytest.raises(PayPalProviderUnavailableError):
                client.get_access_token()
            assert mock_urlopen.call_count == 3  # initial + 2 retries


def test_webhook_verification_requires_webhook_id() -> None:
    client = PayPalClient(client_id="ID", client_secret="SECRET", webhook_id="")
    with pytest.raises(PayPalConfigurationError):
        client.verify_webhook_signature({}, b"{}")


def test_webhook_verification_rejects_missing_headers() -> None:
    client = PayPalClient(client_id="ID", client_secret="SECRET", webhook_id="WH-123")
    headers = {
        "PAYPAL-AUTH-ALGO": "SHA256withRSA",
        # Missing other transmission headers
    }
    assert client.verify_webhook_signature(headers, b"{}") is False


def test_webhook_verification_rejects_invalid_cert_url() -> None:
    client = PayPalClient(client_id="ID", client_secret="SECRET", webhook_id="WH-123")
    headers = {
        "PAYPAL-AUTH-ALGO": "SHA256withRSA",
        "PAYPAL-CERT-URL": "https://evil-hacker.example.com/cert.pem",
        "PAYPAL-TRANSMISSION-ID": "trans-1",
        "PAYPAL-TRANSMISSION-SIG": "sig-1",
        "PAYPAL-TRANSMISSION-TIME": "2026-11-12T14:15:20Z",
    }
    assert client.verify_webhook_signature(headers, b"{}") is False


def test_webhook_verification_success() -> None:
    client = PayPalClient(
        client_id="ID",
        client_secret="SECRET",
        webhook_id="WH-VALID-123",
        base_url="https://api-m.sandbox.paypal.com",
    )
    headers = {
        "PAYPAL-AUTH-ALGO": "SHA256withRSA",
        "PAYPAL-CERT-URL": "https://api-m.sandbox.paypal.com/v1/notifications/certs/CERT-123",
        "PAYPAL-TRANSMISSION-ID": "trans-1",
        "PAYPAL-TRANSMISSION-SIG": "sig-1",
        "PAYPAL-TRANSMISSION-TIME": "2026-11-12T14:15:20Z",
    }
    event_body = json.dumps({"id": "WH-EV-1", "event_type": "PAYMENT.CAPTURE.COMPLETED"}).encode("utf-8")

    with patch.object(client, "get_access_token", return_value="test-token"):
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.read.return_value = json.dumps({"verification_status": "SUCCESS"}).encode("utf-8")

        with patch("urllib.request.urlopen", return_value=mock_response):
            mock_response.__enter__.return_value = mock_response
            assert client.verify_webhook_signature(headers, event_body) is True


def test_webhook_verification_failure_status() -> None:
    client = PayPalClient(
        client_id="ID",
        client_secret="SECRET",
        webhook_id="WH-VALID-123",
    )
    headers = {
        "PAYPAL-AUTH-ALGO": "SHA256withRSA",
        "PAYPAL-CERT-URL": "https://api-m.sandbox.paypal.com/v1/notifications/certs/CERT-123",
        "PAYPAL-TRANSMISSION-ID": "trans-1",
        "PAYPAL-TRANSMISSION-SIG": "forged-sig",
        "PAYPAL-TRANSMISSION-TIME": "2026-11-12T14:15:20Z",
    }
    event_body = json.dumps({"id": "WH-EV-1"}).encode("utf-8")

    with patch.object(client, "get_access_token", return_value="test-token"):
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.read.return_value = json.dumps({"verification_status": "FAILURE"}).encode("utf-8")

        with patch("urllib.request.urlopen", return_value=mock_response):
            mock_response.__enter__.return_value = mock_response
            assert client.verify_webhook_signature(headers, event_body) is False


def test_connectivity_check_reports_missing_credentials() -> None:
    client = PayPalClient(client_id="", client_secret="")
    result = client.verify_connectivity()
    assert result["status"] == "MISSING_CREDENTIALS"


def test_connectivity_check_reports_auth_failure() -> None:
    client = PayPalClient(client_id="ID", client_secret="BAD_SECRET")
    with patch.object(client, "get_access_token", side_effect=PayPalAuthenticationError("Bad credentials")):
        result = client.verify_connectivity()
        assert result["status"] == "AUTHENTICATION_FAILED"


def test_connectivity_check_reports_webhook_missing() -> None:
    client = PayPalClient(client_id="ID", client_secret="SECRET", webhook_id="")
    with patch.object(client, "get_access_token", return_value="token"):
        result = client.verify_connectivity()
        assert result["status"] == "WEBHOOK_NOT_REGISTERED"


def test_connectivity_check_reports_connected_verified() -> None:
    client = PayPalClient(client_id="ID", client_secret="SECRET", webhook_id="WH-123")
    with patch.object(client, "get_access_token", return_value="token"):
        mock_res = MagicMock()
        mock_res.status = 200
        mock_res.read.return_value = json.dumps({"id": "WH-123", "url": "https://example.com/webhook"}).encode("utf-8")
        with patch("urllib.request.urlopen", return_value=mock_res):
            mock_res.__enter__.return_value = mock_res
            result = client.verify_connectivity()
            assert result["status"] == "CONNECTED_VERIFIED"
