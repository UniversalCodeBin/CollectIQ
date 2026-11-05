"""Turns a pasted reply or an uploaded .eml/.txt into plain text. Nothing here is ever rendered as HTML."""

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from email import policy
from email.message import EmailMessage
from email.parser import BytesParser
from email.utils import parseaddr, parsedate_to_datetime
from html.parser import HTMLParser

MAX_CHARS = 100_000
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_BLANKS = re.compile(r"\n{3,}")
_SKIP = {"script", "style", "head", "template", "noscript"}
_BREAKS = {"br", "p", "div", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6", "blockquote"}


@dataclass(frozen=True)
class Parsed:
    text: str
    sender: str | None = None
    subject: str | None = None
    received_at: datetime | None = None


class _Text(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._skipping = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in _SKIP:
            self._skipping += 1
        elif tag in _BREAKS:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in _SKIP and self._skipping:
            self._skipping -= 1
        elif tag in _BREAKS:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self._skipping:
            self.parts.append(data)


def html_to_text(markup: str) -> str:
    """Keeps the words and drops the markup, scripts and styles. Links and images carry nothing through."""
    parser = _Text()
    parser.feed(markup)
    parser.close()
    return "".join(parser.parts)


def clean(text: str) -> str:
    text = _CONTROL.sub("", text.replace("\r\n", "\n").replace("\r", "\n"))
    text = "\n".join(line.rstrip() for line in text.split("\n"))
    return _BLANKS.sub("\n\n", text).strip()[:MAX_CHARS]


def _decode(data: bytes) -> str:
    for charset in ("utf-8", "utf-16"):
        try:
            return data.decode(charset)
        except UnicodeError:
            continue
    return data.decode("latin-1")


def _date(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        parsed = parsedate_to_datetime(raw)
    except (TypeError, ValueError):
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def parse_eml(data: bytes) -> Parsed:
    message = BytesParser(policy=policy.default).parsebytes(data)
    body = message.get_body(preferencelist=("plain", "html")) if isinstance(message, EmailMessage) else None
    text = ""
    if body is not None:
        content = body.get_content()
        text = html_to_text(content) if body.get_content_type() == "text/html" else content
    sender = parseaddr(str(message.get("From", "")))[1] or None
    subject = str(message.get("Subject", "")).strip() or None
    return Parsed(
        clean(text), sender, subject[:500] if subject else None, _date(str(message.get("Date", "")))
    )


def parse_upload(name: str, data: bytes) -> Parsed:
    if name.lower().endswith(".eml"):
        return parse_eml(data)
    return Parsed(clean(_decode(data)))


def parse_paste(text: str) -> Parsed:
    return Parsed(clean(text))
