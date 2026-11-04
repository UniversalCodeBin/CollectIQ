"""Structured logs that cannot carry PII: all scrubbing lives in the one formatter every route uses.

Over-redaction is the accepted failure mode. A log line that lost a number costs less than one that kept
a customer's balance (INV-12, SEC-12).
"""
import json
import logging
import re
import traceback
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any

_correlation_id: ContextVar[str | None] = ContextVar("collectiq_correlation_id", default=None)

_RESERVED = {*logging.makeLogRecord({}).__dict__, "message", "asctime"}

_SENSITIVE_KEY_PARTS = (
    "password", "passwd", "secret", "token", "api_key", "apikey", "authorization", "cookie", "session",
    "credential", "private_key", "email", "phone", "address", "amount", "balance", "total", "body",
    "content", "raw", "payload", "iban", "account_number", "routing", "sort_code", "bank",
)  # fmt: skip

_NUMBER = r"\d[\d,]*(?:\.\d+)?"
# Order matters: credentials go first, since a token can contain what looks like an email or an amount.
_PATTERNS = (
    (re.compile(r"\b(bearer)\s+[\w.~+/=-]+", re.IGNORECASE), r"\1 [redacted]"),
    (
        re.compile(
            r"\b(token|api[_-]?key|secret|password|passwd|authorization|cookie|session(?:_?id)?|credential)"
            r"\w*[\"']?\s*[=:]\s*[\"']?[^\s,;\"']+",
            re.IGNORECASE,
        ),
        r"\1=[redacted]",
    ),
    (re.compile(r"\beyJ[\w-]+\.[\w-]+\.[\w-]+"), "[token]"),
    (re.compile(r"[A-Za-z0-9_+/=]{32,}"), "[token]"),  # no dash, so a UUID survives
    (re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+"), "[email]"),
    (
        re.compile(
            rf"[\"']?\b\w*(?:amount|balance|total)\w*[\"']?\s*[=:]\s*[\"']?-?{_NUMBER}", re.IGNORECASE
        ),
        "[amount]",
    ),
    (re.compile(rf"[₹$€£¥]\s?{_NUMBER}"), "[amount]"),
    (re.compile(rf"\b[A-Z]{{3}}\s?{_NUMBER}"), "[amount]"),
    (re.compile(rf"\b{_NUMBER}\s?[A-Z]{{3}}\b"), "[amount]"),
    (re.compile(r"\b\d{1,3}(?:,\d{2,3})+(?:\.\d+)?\b"), "[amount]"),
    (re.compile(r"\b\d+\.\d{2}\b"), "[amount]"),
)


def scrub(text: str) -> str:
    for pattern, replacement in _PATTERNS:
        text = pattern.sub(replacement, text)
    return text


def _is_sensitive(key: object) -> bool:
    lowered = str(key).lower()
    return any(part in lowered for part in _SENSITIVE_KEY_PARTS)


def _scrub_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _scrub_value(item) for key, item in value.items() if not _is_sensitive(key)}
    if isinstance(value, list | tuple | set):
        return [_scrub_value(item) for item in value]
    if value is None or isinstance(value, bool | int | float):
        return value
    return scrub(str(value))


class ScrubbingJsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        extras = {key: value for key, value in record.__dict__.items() if key not in _RESERVED}
        entry = {
            **_scrub_value(extras),
            "ts": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": scrub(record.getMessage()),
        }
        correlation_id = _correlation_id.get()
        if correlation_id is not None:
            entry["correlation_id"] = correlation_id
        if record.exc_info and record.exc_info[0] is not None:
            # Frames and the class, never the message: exception text is where row data escapes to.
            kind, _, trace = record.exc_info
            entry["exception"] = "".join(traceback.format_tb(trace)) + kind.__name__
        return json.dumps(entry, ensure_ascii=False)


def current_correlation_id() -> str | None:
    return _correlation_id.get()


@contextmanager
def bind_correlation_id(correlation_id: str) -> Iterator[None]:
    token = _correlation_id.set(correlation_id)
    try:
        yield
    finally:
        _correlation_id.reset(token)
