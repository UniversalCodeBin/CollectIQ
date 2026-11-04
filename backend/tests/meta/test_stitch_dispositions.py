"""Every interactive control in the Stitch exports has a recorded decision."""
import importlib.util
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
SCRIPT = REPO / "scripts" / "extract_stitch_controls.py"
DISPOSITIONS = REPO / "docs" / "stitch-control-dispositions.md"
ALLOWED = {"KEEP", "CHANGE", "OMIT"}


def _load():
    spec = importlib.util.spec_from_file_location("extract_stitch_controls", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_icon_font_text_is_not_a_label():
    html = '<button><span class="material-symbols-outlined">add</span>Add client</button>'
    assert _load().extract(html) == [("button", "Add client")]


def test_icon_only_button_falls_back_to_aria_label():
    html = '<button aria-label="Close"><span class="material-symbols-outlined">close</span></button>'
    assert _load().extract(html) == [("button", "Close")]


def test_input_is_captured_by_type_and_placeholder():
    html = '<input type="search" placeholder="Search clients"/>'
    assert _load().extract(html) == [("search", "Search clients")]


def test_script_and_style_contents_are_ignored():
    html = '<script>var s = "<button>Ghost</button>";</script><style>a{}</style><a href="#">Real</a>'
    assert _load().extract(html) == [("a", "Real")]


def _disposition_rows() -> dict[tuple[str, str], str]:
    rows = {}
    for line in DISPOSITIONS.read_text(encoding="utf-8").splitlines():
        cells = [cell.strip() for cell in line.split(" | ")]
        if len(cells) >= 4 and cells[0].startswith("| ") and cells[0][2:] not in {"kind", "---"}:
            rows[(cells[0][2:], cells[1])] = cells[3]
    return rows


def _key(kind: str, label: str) -> tuple[str, str]:
    return kind, (label.replace("|", "\\|") if label else "(no label)")


def _inventory() -> set[tuple[str, str]]:
    module = _load()
    found = set()
    for page in sorted(module.STITCH.glob("*/code.html")):
        for kind, label in module.extract(page.read_text(encoding="utf-8")):
            found.add(_key(kind, label))
    return found


def test_every_stitch_control_has_a_disposition():
    rows = _disposition_rows()
    missing = sorted(_inventory() - set(rows))
    assert not missing, f"{len(missing)} controls have no disposition, first: {missing[:5]}"


def test_every_disposition_is_a_known_decision():
    bad = {key: value for key, value in _disposition_rows().items() if value not in ALLOWED}
    assert not bad, f"unknown dispositions: {list(bad.items())[:5]}"
