#!/usr/bin/env python3
"""List every interactive control in the Stitch exports, one row per screen and label.

The output is the input to the disposition table in docs/stitch-control-dispositions.md, so that
every control in the designs is accounted for rather than sampled.
"""
import json
import sys
from html.parser import HTMLParser
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
STITCH = REPO / "stitch_collectiq_receivables_copilot"
CONTROL_TAGS = {"button", "a", "input", "select", "textarea", "summary"}
VOID_TAGS = {"input"}
ICON_FONT_CLASS = "material-symbols"


class ControlParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.controls: list[tuple[str, str]] = []
        self.open: list[dict] = []
        self.icon_depth = 0
        self.span_stack: list[bool] = []

    def handle_starttag(self, tag: str, attrs: list) -> None:
        attributes = dict(attrs)
        if tag == "span":
            is_icon = ICON_FONT_CLASS in (attributes.get("class") or "")
            self.span_stack.append(is_icon)
            self.icon_depth += is_icon
        if tag not in CONTROL_TAGS:
            return
        hint = attributes.get("aria-label") or attributes.get("placeholder") or attributes.get("value") or ""
        kind = attributes.get("type", tag) if tag == "input" else tag
        if tag in VOID_TAGS:
            self.controls.append((kind, hint))
        else:
            self.open.append({"kind": kind, "hint": hint, "text": []})

    def handle_endtag(self, tag: str) -> None:
        if tag == "span" and self.span_stack:
            self.icon_depth -= self.span_stack.pop()
        if tag in CONTROL_TAGS and tag not in VOID_TAGS and self.open:
            control = self.open.pop()
            label = " ".join(" ".join(control["text"]).split()) or control["hint"]
            self.controls.append((control["kind"], label))

    def handle_data(self, data: str) -> None:
        if self.open and not self.icon_depth and data.strip():
            self.open[-1]["text"].append(data.strip())


def extract(html: str) -> list[tuple[str, str]]:
    parser = ControlParser()
    parser.feed(html)
    return parser.controls


def main() -> int:
    inventory: dict[str, list[list]] = {}
    for page in sorted(STITCH.glob("*/code.html")):
        counts: dict[tuple[str, str], int] = {}
        for control in extract(page.read_text(encoding="utf-8")):
            counts[control] = counts.get(control, 0) + 1
        inventory[page.parent.name] = [[kind, label, n] for (kind, label), n in sorted(counts.items())]
    json.dump(inventory, sys.stdout, indent=1, ensure_ascii=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
