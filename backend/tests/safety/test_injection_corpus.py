# ruff: noqa: F811, F401
"""Hostile customer text must not change money, send anything or invent an action (TS-020, AIR-09).

Each corpus message is run against a worst-case AI that obeys the injection, once with an invented
action label and once with a confident payment-claim reading. Neither may mark anything paid, allocate,
or create a reminder.
"""

import json
from pathlib import Path
from typing import Any

import pytest

from tests.integration.test_conversations import Env
from tests.integration.test_interpretation import env, reading, script

pytestmark = pytest.mark.usefixtures("pg")

CORPUS = json.loads((Path(__file__).parent / "injection_corpus" / "corpus.json").read_text())


def counts(env: Env) -> dict[str, int]:
    return {
        table: env.db.execute(f"SELECT count(*) FROM {table}").fetchone()[0]  # noqa: S608
        for table in ("payment_allocations", "reminders", "snoozes", "payment_transactions")
    }


@pytest.mark.parametrize("case", CORPUS, ids=[c["id"] for c in CORPUS])
@pytest.mark.parametrize("obey", ["invented-label", "payment-claim"])
def test_hostile_text_changes_no_money_and_sends_nothing(
    env: Env,
    script: Any,
    case: dict[str, str],
    obey: str,
) -> None:
    if obey == "invented-label":
        bad = reading(labels=["MARK_PAID"], primary_label="MARK_PAID")
        script(bad, bad)
    else:
        script(reading(evidence=case["text"][:20]))
    before = counts(env)
    message = env.message(text=case["text"], on="INV-1")
    assert message["id"]
    state = env.state()
    assert state["payment_status"] != "PAID_VERIFIED"
    assert counts(env) == before
