"""Queues the nightly maintenance jobs: audit chain check, evidence integrity check, retention.

Run it once a day from cron, a systemd timer or a scheduler container. The dedupe key is the date, so a second
run on the same day adds nothing. The workers do the work.
"""

import logging
from typing import Any
from uuid import UUID

from django.core.management.base import BaseCommand
from django.db import connection

from collectiq.platform import clock, jobs
from collectiq.platform.context import RequestContext
from collectiq.platform.db import tenant_tx

logger = logging.getLogger(__name__)

NIGHTLY_KINDS = ("audit.verify_chain", "evidence.integrity_check", "privacy.retention")


def _workspace_ids() -> list[UUID]:
    with connection.cursor() as cursor:
        cursor.execute("SELECT * FROM workspace_ids_for_schedule()")
        return [row[0] for row in cursor.fetchall()]


class Command(BaseCommand):
    help = "Queue today's maintenance jobs for every workspace."

    def handle(self, *args: Any, **options: Any) -> None:
        day = clock.today().isoformat()
        workspaces = _workspace_ids()
        for workspace_id in workspaces:
            ctx = RequestContext(
                workspace_id=workspace_id,
                user_id=None,
                role=None,
                correlation_id=f"nightly-{day}",
                actor_type="SYSTEM",
            )
            with tenant_tx(ctx):
                for kind in NIGHTLY_KINDS:
                    jobs.enqueue(ctx, kind, {}, dedupe_key=f"nightly-{day}")
        self.stdout.write(f"queued {len(NIGHTLY_KINDS)} jobs for {len(workspaces)} workspaces")
