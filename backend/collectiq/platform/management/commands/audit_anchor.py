"""Prints each workspace's audit chain head so it can be stored OFF the database host.

FILE GUIDE: `audit_anchor` writes JSON lines {workspace_id, last_id, events, head_hash}. Keep the output
somewhere the database operator cannot rewrite (a different account's bucket, a ticket, a signed email).
`audit_anchor --check FILE` re-reads the chain and reports any anchored workspace whose chain no longer
contains the anchored event with the same hash. That catches a rewrite of past rows by someone who can also
recompute hashes, which the in-database chain alone cannot. It does not stop a superuser; it makes the change
detectable if the anchor was stored elsewhere before it.
"""

import json
from typing import Any
from uuid import UUID

from django.core.management.base import BaseCommand, CommandError
from django.db import connection

from collectiq.platform import clock
from collectiq.platform.context import RequestContext
from collectiq.platform.db import tenant_tx

from .schedule_nightly import _workspace_ids


def _ctx(workspace_id: UUID) -> RequestContext:
    return RequestContext(
        workspace_id=workspace_id, user_id=None, role=None, correlation_id="audit-anchor", actor_type="SYSTEM"
    )


def _head(workspace_id: UUID) -> dict[str, Any]:
    ctx = _ctx(workspace_id)
    with tenant_tx(ctx), connection.cursor() as cursor:
        cursor.execute("SELECT count(*), max(id) FROM audit_events")
        events, last_id = cursor.fetchone()
        cursor.execute("SELECT encode(hash, 'hex') FROM audit_events WHERE id = %s", [last_id])
        row = cursor.fetchone()
    head = row[0] if row else None
    return {"workspace_id": str(workspace_id), "last_id": last_id, "events": events, "head_hash": head}


def _hash_at(workspace_id: UUID, event_id: int) -> str | None:
    ctx = _ctx(workspace_id)
    with tenant_tx(ctx), connection.cursor() as cursor:
        cursor.execute("SELECT encode(hash, 'hex') FROM audit_events WHERE id = %s", [event_id])
        row = cursor.fetchone()
    return row[0] if row else None


class Command(BaseCommand):
    help = "Print the audit chain head per workspace, or --check a stored anchor file."

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument("--check", metavar="FILE", help="Compare a stored anchor file with the database.")

    def handle(self, *args: Any, **options: Any) -> None:
        if options["check"]:
            return self._check(options["check"])
        for workspace_id in _workspace_ids():
            self.stdout.write(json.dumps({**_head(workspace_id), "anchored_on": clock.today().isoformat()}))

    def _check(self, path: str) -> None:
        bad = 0
        with open(path, encoding="utf-8") as handle:
            for line in filter(str.strip, handle):
                anchor = json.loads(line)
                if anchor["last_id"] is None:
                    continue
                now = _hash_at(UUID(anchor["workspace_id"]), anchor["last_id"])
                if now != anchor["head_hash"]:
                    bad += 1
                    self.stdout.write(f"MISMATCH {anchor['workspace_id']} event {anchor['last_id']}")
        if bad:
            raise CommandError(f"{bad} workspace chain(s) no longer match the stored anchor")
        self.stdout.write("all anchored chain heads still match")
