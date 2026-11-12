"""PayPal REST API Client for Sandbox and Live environments.

Handles OAuth 2.0 client credentials authentication, token caching,
webhook signature verification, connectivity verification, and resilient
HTTP transport with exponential backoff and jitter.
"""

import base64
import json
import logging
import random
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Mapping
from typing import Any
from urllib.parse import urlparse

from django.conf import settings

logger = logging.getLogger("collectiq.integrations.paypal")

# Sandbox default base URL
SANDBOX_BASE_URL = "https://api-m.sandbox.paypal.com"
LIVE_BASE_URL = "https://api-m.paypal.com"

# Required transmission headers for webhook verification
REQUIRED_WEBHOOK_HEADERS = (
    "PAYPAL-AUTH-ALGO",
    "PAYPAL-CERT-URL",
    "PAYPAL-TRANSMISSION-ID",
    "PAYPAL-TRANSMISSION-SIG",
    "PAYPAL-TRANSMISSION-TIME",
)

# Valid PayPal certificate hosts
VALID_CERT_HOSTS = (
    "api.paypal.com",
    "api.sandbox.paypal.com",
    "api-m.paypal.com",
    "api-m.sandbox.paypal.com",
    "notify.paypal.com",
)


class PayPalError(Exception):
    """Base exception for PayPal provider operations."""


class PayPalMissingCredentialsError(PayPalError):
    """Raised when Client ID or Secret is not configured."""


class PayPalAuthenticationError(PayPalError):
    """Raised when PayPal returns HTTP 401 Unauthorized."""


class PayPalPermissionError(PayPalError):
    """Raised when PayPal returns HTTP 403 Forbidden."""


class PayPalRateLimitError(PayPalError):
    """Raised when PayPal returns HTTP 429 Too Many Requests."""


class PayPalProviderUnavailableError(PayPalError):
    """Raised when PayPal returns 5xx or fails at network level."""


class PayPalConfigurationError(PayPalError):
    """Raised when PayPal client configuration or webhook registration is invalid."""


def redact_sensitive(val: Any) -> Any:
    """Recursively mask secrets and tokens in dictionaries/strings for safe logging."""
    if isinstance(val, dict):
        return {k: ("***REDACTED***" if any(s in k.lower() for s in ("secret", "token", "auth", "sig", "key")) else redact_sensitive(v)) for k, v in val.items()}
    if isinstance(val, list):
        return [redact_sensitive(v) for v in val]
    return val


def get_header(headers: Mapping[str, str], name: str) -> str | None:
    """Retrieve header value case-insensitively, handling HTTP_ prefix."""
    target = name.upper()
    http_target = f"HTTP_{target.replace('-', '_')}"
    for k, v in headers.items():
        k_upper = k.upper().replace("-", "_")
        if k_upper == target.replace("-", "_") or k_upper == http_target:
            return v
    return None


class PayPalClient:
    """Server-side client for PayPal REST API."""

    def __init__(
        self,
        environment: str | None = None,
        base_url: str | None = None,
        client_id: str | None = None,
        client_secret: str | None = None,
        webhook_id: str | None = None,
        connect_timeout: float = 5.0,
        read_timeout: float = 10.0,
        max_retries: int = 3,
    ) -> None:
        self.environment = (environment or getattr(settings, "PAYPAL_ENVIRONMENT", "sandbox")).lower()
        if self.environment == "sandbox":
            self.base_url = (base_url or getattr(settings, "PAYPAL_BASE_URL", SANDBOX_BASE_URL)).rstrip("/")
        else:
            self.base_url = (base_url or getattr(settings, "PAYPAL_BASE_URL", LIVE_BASE_URL)).rstrip("/")

        self.client_id = (client_id if client_id is not None else getattr(settings, "PAYPAL_CLIENT_ID", "")).strip()
        self.client_secret = (client_secret if client_secret is not None else getattr(settings, "PAYPAL_CLIENT_SECRET", "")).strip()
        self.webhook_id = (webhook_id if webhook_id is not None else getattr(settings, "PAYPAL_WEBHOOK_ID", "")).strip()

        self.connect_timeout = connect_timeout
        self.read_timeout = read_timeout
        self.max_retries = max_retries

        self._cached_token: str | None = None
        self._token_expires_at: float = 0.0
        self._lock = threading.Lock()

    def is_configured(self) -> bool:
        """True if credentials are non-empty."""
        return bool(self.client_id and self.client_secret)

    def _request(
        self,
        method: str,
        path: str,
        headers: dict[str, str] | None = None,
        data: bytes | None = None,
        is_retryable: bool = True,
    ) -> tuple[int, dict[str, Any]]:
        """Executes HTTP request with exponential backoff and jitter for retryable errors."""
        url = f"{self.base_url}{path}"
        req_headers = headers or {}
        req_headers.setdefault("User-Agent", "CollectIQ-PayPal-Adapter/1.0")

        delay = 0.5
        attempt = 0
        last_error: Exception | None = None

        while attempt <= (self.max_retries if is_retryable else 0):
            attempt += 1
            try:
                req = urllib.request.Request(url, data=data, headers=req_headers, method=method)
                with urllib.request.urlopen(req, timeout=self.read_timeout) as response:
                    status = response.status
                    body = response.read()
                    parsed_body: dict[str, Any] = {}
                    if body:
                        try:
                            parsed_body = json.loads(body.decode("utf-8"))
                        except Exception:
                            parsed_body = {"raw": body.decode("utf-8", errors="replace")}
                    return status, parsed_body

            except urllib.error.HTTPError as exc:
                status = exc.code
                error_body = exc.read().decode("utf-8", errors="replace")
                parsed_error: dict[str, Any] = {}
                try:
                    parsed_error = json.loads(error_body)
                except Exception:
                    parsed_error = {"message": error_body}

                # Classification
                if status == 401:
                    logger.warning("PayPal API authentication failure (401) on %s", path)
                    raise PayPalAuthenticationError(parsed_error.get("error_description") or "Authentication failed") from exc
                if status == 403:
                    logger.warning("PayPal API permission denied (403) on %s", path)
                    raise PayPalPermissionError(parsed_error.get("message") or "Permission denied") from exc
                if status == 429:
                    logger.warning("PayPal API rate limited (429) on %s", path)
                    if not is_retryable or attempt > self.max_retries:
                        raise PayPalRateLimitError("Rate limit exceeded") from exc
                elif 500 <= status < 600:
                    logger.warning("PayPal API server error (%s) on %s", status, path)
                    if not is_retryable or attempt > self.max_retries:
                        raise PayPalProviderUnavailableError(f"PayPal server error {status}") from exc
                else:
                    # 4xx client errors that are not retryable
                    raise PayPalError(f"PayPal API error {status}: {parsed_error}") from exc

                last_error = exc

            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                logger.warning("PayPal API network error on %s: %s (attempt %d/%d)", path, exc, attempt, self.max_retries)
                if not is_retryable or attempt > self.max_retries:
                    raise PayPalProviderUnavailableError(f"PayPal unreachable: {exc}") from exc
                last_error = exc

            # Backoff with jitter before retrying
            jitter = random.uniform(0.1, 0.4)
            sleep_time = delay + jitter
            time.sleep(sleep_time)
            delay *= 2.0

        if last_error:
            raise PayPalProviderUnavailableError(f"Failed after {self.max_retries} retries: {last_error}") from last_error
        raise PayPalProviderUnavailableError("Unknown network error")

    def get_access_token(self, force_refresh: bool = False) -> str:
        """Retrieves and caches OAuth 2.0 client credentials token."""
        if not self.is_configured():
            raise PayPalMissingCredentialsError("PAYPAL_CLIENT_ID or PAYPAL_CLIENT_SECRET is missing.")

        now = time.time()
        if not force_refresh and self._cached_token and now < (self._token_expires_at - 60):
            return self._cached_token

        with self._lock:
            # Double-check inside lock
            if not force_refresh and self._cached_token and now < (self._token_expires_at - 60):
                return self._cached_token

            auth_str = f"{self.client_id}:{self.client_secret}"
            b64_auth = base64.b64encode(auth_str.encode("utf-8")).decode("ascii")

            headers = {
                "Authorization": f"Basic {b64_auth}",
                "Accept": "application/json",
                "Accept-Language": "en_US",
                "Content-Type": "application/x-www-form-urlencoded",
            }
            body = b"grant_type=client_credentials"

            logger.info("Requesting PayPal OAuth access token from %s/v1/oauth2/token", self.base_url)
            status, data = self._request("POST", "/v1/oauth2/token", headers=headers, data=body, is_retryable=True)

            token = data.get("access_token")
            expires_in = int(data.get("expires_in", 3600))
            if not token:
                raise PayPalAuthenticationError("PayPal OAuth response missing access_token.")

            self._cached_token = str(token)
            self._token_expires_at = time.time() + expires_in
            logger.info(
                "Acquired PayPal OAuth token (app_id=%s, expires_in=%ds, env=%s)",
                data.get("app_id", "unknown"),
                expires_in,
                self.environment,
            )
            return self._cached_token

    def _authenticated_request(
        self,
        method: str,
        path: str,
        headers: dict[str, str] | None = None,
        data: bytes | None = None,
        is_retryable: bool = True,
    ) -> tuple[int, dict[str, Any]]:
        """Executes request with Bearer token, auto-refreshing on 401 once."""
        token = self.get_access_token()
        req_headers = headers.copy() if headers else {}
        req_headers["Authorization"] = f"Bearer {token}"
        req_headers.setdefault("Content-Type", "application/json")

        try:
            return self._request(method, path, headers=req_headers, data=data, is_retryable=is_retryable)
        except PayPalAuthenticationError:
            # Token might have been revoked; force refresh once
            logger.info("PayPal returned 401 with cached token, refreshing token once...")
            token = self.get_access_token(force_refresh=True)
            req_headers["Authorization"] = f"Bearer {token}"
            return self._request(method, path, headers=req_headers, data=data, is_retryable=is_retryable)

    def verify_webhook_signature(self, headers: Mapping[str, str], body: bytes) -> bool:
        """Verifies an incoming webhook notification using PayPal's verification API.

        POST /v1/notifications/verify-webhook-signature
        """
        if not self.webhook_id:
            logger.error("Cannot verify webhook signature: PAYPAL_WEBHOOK_ID is not configured.")
            raise PayPalConfigurationError("PAYPAL_WEBHOOK_ID is not configured.")

        # Check required headers
        auth_algo = get_header(headers, "PAYPAL-AUTH-ALGO")
        cert_url = get_header(headers, "PAYPAL-CERT-URL")
        transmission_id = get_header(headers, "PAYPAL-TRANSMISSION-ID")
        transmission_sig = get_header(headers, "PAYPAL-TRANSMISSION-SIG")
        transmission_time = get_header(headers, "PAYPAL-TRANSMISSION-TIME")

        missing = [h for h, v in [
            ("PAYPAL-AUTH-ALGO", auth_algo),
            ("PAYPAL-CERT-URL", cert_url),
            ("PAYPAL-TRANSMISSION-ID", transmission_id),
            ("PAYPAL-TRANSMISSION-SIG", transmission_sig),
            ("PAYPAL-TRANSMISSION-TIME", transmission_time),
        ] if not v]

        if missing:
            logger.warning("PayPal webhook verification rejected: missing headers: %s", missing)
            return False

        # Validate cert_url safety (must be official PayPal domain)
        parsed_cert = urlparse(cert_url or "")
        if parsed_cert.scheme != "https" or parsed_cert.netloc not in VALID_CERT_HOSTS:
            logger.warning("PayPal webhook verification rejected: untrusted cert_url: %s", cert_url)
            return False

        # Parse event JSON
        try:
            event_obj = json.loads(body.decode("utf-8"))
        except Exception:
            logger.warning("PayPal webhook verification rejected: payload is not valid JSON")
            return False

        verify_payload = {
            "auth_algo": auth_algo,
            "cert_url": cert_url,
            "transmission_id": transmission_id,
            "transmission_sig": transmission_sig,
            "transmission_time": transmission_time,
            "webhook_id": self.webhook_id,
            "webhook_event": event_obj,
        }

        try:
            status, response_data = self._authenticated_request(
                "POST",
                "/v1/notifications/verify-webhook-signature",
                data=json.dumps(verify_payload).encode("utf-8"),
                is_retryable=True,
            )
        except Exception as exc:
            logger.error("Failed to reach PayPal verify-webhook-signature endpoint: %s", exc)
            return False

        verification_status = response_data.get("verification_status")
        is_success = verification_status == "SUCCESS"
        logger.info(
            "PayPal webhook verification result: %s (transmission_id=%s, event_id=%s)",
            verification_status,
            transmission_id,
            event_obj.get("id"),
        )
        return is_success

    def verify_connectivity(self) -> dict[str, Any]:
        """Performs a real API authentication and configuration check.

        Returns structured status:
        - CONNECTED_VERIFIED
        - MISSING_CREDENTIALS
        - AUTHENTICATION_FAILED
        - PROVIDER_UNAVAILABLE
        - CONFIGURATION_ERROR
        - WEBHOOK_NOT_REGISTERED
        """
        if not self.is_configured():
            return {
                "status": "MISSING_CREDENTIALS",
                "message": "PAYPAL_CLIENT_ID or PAYPAL_CLIENT_SECRET is missing in server environment.",
                "environment": self.environment,
                "webhook_status": "MISSING" if not self.webhook_id else "CONFIGURED",
            }

        try:
            self.get_access_token(force_refresh=True)
        except PayPalAuthenticationError as exc:
            return {
                "status": "AUTHENTICATION_FAILED",
                "message": f"Authentication failed: {exc}",
                "environment": self.environment,
                "webhook_status": "UNKNOWN",
            }
        except PayPalProviderUnavailableError as exc:
            return {
                "status": "PROVIDER_UNAVAILABLE",
                "message": f"PayPal API unreachable: {exc}",
                "environment": self.environment,
                "webhook_status": "UNKNOWN",
            }
        except Exception as exc:
            return {
                "status": "CONFIGURATION_ERROR",
                "message": f"Configuration error: {exc}",
                "environment": self.environment,
                "webhook_status": "UNKNOWN",
            }

        # Check webhook registration if webhook_id provided
        if not self.webhook_id:
            return {
                "status": "WEBHOOK_NOT_REGISTERED",
                "message": "Authentication succeeded, but PAYPAL_WEBHOOK_ID is not configured.",
                "environment": self.environment,
                "webhook_status": "MISSING",
            }

        try:
            status, data = self._authenticated_request("GET", f"/v1/notifications/webhooks/{self.webhook_id}")
            if status == 200:
                return {
                    "status": "CONNECTED_VERIFIED",
                    "message": "Connected and verified with PayPal Sandbox REST API.",
                    "environment": self.environment,
                    "webhook_id": self.webhook_id,
                    "webhook_status": "CONFIGURED",
                    "webhook_url": data.get("url"),
                }
        except PayPalError as exc:
            logger.warning("Webhook inspection error on %s: %s", self.webhook_id, exc)
            return {
                "status": "WEBHOOK_NOT_REGISTERED",
                "message": f"Webhook ID '{self.webhook_id}' was not found or accessible on PayPal.",
                "environment": self.environment,
                "webhook_status": "UNVERIFIED",
            }

        return {
            "status": "CONNECTED_VERIFIED",
            "message": "Connected and verified with PayPal Sandbox REST API.",
            "environment": self.environment,
            "webhook_id": self.webhook_id,
            "webhook_status": "CONFIGURED",
        }
