"""The Gmail port. Nothing here has been verified against Google; the default refuses rather than pretends."""

import hashlib
from base64 import urlsafe_b64encode
from dataclasses import dataclass, field
from typing import Any, Protocol

SEND_SCOPE = "https://www.googleapis.com/auth/gmail.send"


class ProviderRejected(Exception):
    """The provider definitely refused the message. Nothing was sent."""


class ProviderUnknown(Exception):
    """The connection failed after the message may have left. The outcome cannot be known."""


class NotConfigured(Exception):
    """No transport is configured in this deployment."""


class GmailTransport(Protocol):
    def authorization_url(self, state: str, challenge: str) -> str: ...

    def exchange(self, code: str, verifier: str) -> dict[str, Any]:
        """Returns {"refresh_token": str, "scopes": list[str]}."""

    def send(self, credential: str, to: str, subject: str, body: str) -> str:
        """Returns the provider message id. Raises ProviderRejected or ProviderUnknown."""

    def revoke(self, credential: str) -> None: ...


class UnconfiguredTransport:
    def _refuse(self) -> Any:
        raise NotConfigured("Gmail has no live transport in this deployment.")

    def authorization_url(self, state: str, challenge: str) -> str:
        return str(self._refuse())

    def exchange(self, code: str, verifier: str) -> dict[str, Any]:
        return dict(self._refuse())

    def send(self, credential: str, to: str, subject: str, body: str) -> str:
        return str(self._refuse())

    def revoke(self, credential: str) -> None:
        self._refuse()


@dataclass
class FakeTransport:
    grant_scopes: tuple[str, ...] = (SEND_SCOPE,)
    refresh_token: str = "fake-refresh-token-0123456789"  # noqa: S105
    exchanged: list[dict[str, Any]] = field(default_factory=list)
    sent: list[dict[str, Any]] = field(default_factory=list)
    attempts: list[dict[str, Any]] = field(default_factory=list)
    script: list[str] = field(default_factory=list)
    revoked: list[str] = field(default_factory=list)

    def authorization_url(self, state: str, challenge: str) -> str:
        from urllib.parse import urlencode

        query = urlencode(
            {
                "scope": SEND_SCOPE,
                "state": state,
                "code_challenge": challenge,
                "code_challenge_method": "S256",
                "response_type": "code",
            }
        )
        return f"https://accounts.example.test/o/oauth2/v2/auth?{query}"

    def exchange(self, code: str, verifier: str) -> dict[str, Any]:
        self.exchanged.append({"code": code, "verifier": verifier})
        return {"refresh_token": self.refresh_token, "scopes": list(self.grant_scopes)}

    def send(self, credential: str, to: str, subject: str, body: str) -> str:
        self.attempts.append({"to": to})
        step = self.script.pop(0) if self.script else "ok"
        if step == "reject":
            raise ProviderRejected("rejected")
        if step == "drop":
            raise ProviderUnknown("connection dropped")
        self.sent.append({"to": to, "subject": subject, "body": body})
        return "fake-" + hashlib.sha256(urlsafe_b64encode(body.encode())).hexdigest()[:12]

    def revoke(self, credential: str) -> None:
        self.revoked.append(credential)


_transport: GmailTransport | None = None


def set_transport(transport: GmailTransport | None) -> None:
    global _transport
    _transport = transport


def get_transport() -> GmailTransport:
    return _transport or UnconfiguredTransport()
