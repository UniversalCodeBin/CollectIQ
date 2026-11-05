"""Replaces identifiers with stable tokens before anything is sent. The mapping never leaves this process."""

import re

_EMAIL = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
_ACCOUNT = re.compile(r"\b(?:[A-Z]{2}\d{2}[A-Z0-9]{10,30}|\d(?:[ -]?\d){7,18})\b")
_PHONE = re.compile(r"(?<![\w])\+?\(?\d[\d\s().\-]{6,}\d(?![\w])")


class Redactor:
    def __init__(self) -> None:
        self._tokens: dict[tuple[str, str], str] = {}
        self._counts: dict[str, int] = {}

    def _token(self, kind: str, value: str) -> str:
        key = (kind, value.lower() if kind == "EMAIL" else value)
        if key not in self._tokens:
            self._counts[kind] = self._counts.get(kind, 0) + 1
            self._tokens[key] = f"[{kind}_{self._counts[kind]}]"
        return self._tokens[key]

    def text(self, value: str) -> str:
        value = _EMAIL.sub(lambda m: self._token("EMAIL", m.group()), value)
        # Long digit runs are accounts; the rest of the phone-shaped runs are phones.
        value = _ACCOUNT.sub(
            lambda m: self._token("ACCOUNT", m.group()) if _digits(m.group()) >= 9 else m.group(), value
        )
        return _PHONE.sub(
            lambda m: self._token("PHONE", m.group()) if _digits(m.group()) >= 7 else m.group(), value
        )

    def name(self, value: str) -> str:
        return self._token("CLIENT", value)

    @property
    def counts(self) -> dict[str, int]:
        return dict(self._counts)


def _digits(text: str) -> int:
    return sum(ch.isdigit() for ch in text)
