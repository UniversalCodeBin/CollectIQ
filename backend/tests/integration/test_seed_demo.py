"""The demo seed gives one working login per role, can be run twice, and is refused in production."""

from typing import Any

import pytest
from django.core.management import CommandError, call_command

from collectiq.identity import service as identity
from collectiq.invoices.management.commands.seed_demo import DEMO_PASSWORD, DEMO_USERS, DEMO_WORKSPACE_ID
from collectiq.tenancy.service import role_in

pytestmark = pytest.mark.usefixtures("pg")


def test_seed_demo_refused_in_production(settings: Any) -> None:
    settings.DJANGO_ENV = "production"
    with pytest.raises(CommandError, match="production"):
        call_command("seed_demo")


def test_each_demo_role_can_log_in_and_runs_twice() -> None:
    call_command("seed_demo", invoices=5)
    call_command("seed_demo", invoices=5)
    for email, role in DEMO_USERS:
        _token, user = identity.login(email, DEMO_PASSWORD, "seed-demo-test", None)
        assert role_in(user["id"], DEMO_WORKSPACE_ID) == role
