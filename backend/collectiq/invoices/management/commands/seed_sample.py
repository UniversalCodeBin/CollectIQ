"""Fills a workspace with clearly labelled sample invoices so the queue can be tried without real data."""

import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Any

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from collectiq.audit import record
from collectiq.platform.context import RequestContext
from collectiq.platform.db import execute, execute_many, fetch_one, tenant_tx

from ...domain.validate import normalize_name, normalize_number  # noqa: TID252
from ...state import create_states  # noqa: TID252

SOURCE = "SAMPLE"
CLIENTS = ("Northwind Traders", "Contoso Supplies", "Fabrikam Works", "Tailspin Logistics", "Lakeside Studio")
# (days from today the invoice is due, state changes). Cycled so every queue reason shows up.
_SHAPES: tuple[tuple[int, dict[str, Any]], ...] = (
    (-45, {}),
    (-12, {}),
    (-3, {"reminder_status": "DRAFT_READY"}),
    (5, {}),
    (-20, {"dispute_status": "OPEN"}),
    (-8, {"payment_status": "AWAITING_VERIFICATION"}),
    (-30, {"payment_status": "PARTIALLY_PAID", "paid_percent": 40}),
    (14, {"reminder_status": "SNOOZED", "snooze_days": 10}),
    (-70, {"payment_status": "UNCERTAIN"}),
    (-100, {}),
)


class Command(BaseCommand):
    help = "Create labelled sample invoices in one workspace. Refused in production."

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument("--workspace", required=True, help="Workspace id")
        parser.add_argument("--invoices", type=int, default=30)

    def handle(self, *args: Any, **options: Any) -> None:
        if settings.DJANGO_ENV == "production":
            raise CommandError("Sample data is never created in production.")
        count = int(options["invoices"])
        if not 1 <= count <= 5000:
            raise CommandError("Use between 1 and 5000 invoices.")
        ctx = RequestContext(uuid.UUID(str(options["workspace"])), None, None, str(uuid.uuid4()), "SYSTEM")
        with tenant_tx(ctx):
            if fetch_one("SELECT 1 AS found FROM workspaces LIMIT 1") is None:
                raise CommandError("That workspace does not exist.")
            self._create(ctx, count)
            record(ctx, "workspace.sample_data_seeded", "workspace", str(ctx.workspace_id),
                   after={"invoices": count, "source_system": SOURCE})  # fmt: skip
        self.stdout.write(f"Created {count} sample invoices, labelled {SOURCE}.")

    def _create(self, ctx: RequestContext, count: int) -> None:
        today = datetime.now(UTC).date()
        clients = []
        for index, name in enumerate(CLIENTS):
            client_id = uuid.uuid4()
            clients.append(client_id)
            execute(
                "INSERT INTO clients (workspace_id, id, display_name, normalized_name)"
                " VALUES (%s, %s, %s, %s)",
                [ctx.workspace_id, client_id, name, normalize_name(name)],
            )
            execute(
                "INSERT INTO client_contacts (workspace_id, client_id, email, name) VALUES (%s, %s, %s, %s)",
                [ctx.workspace_id, client_id, f"accounts{index}@example.test", "Accounts"],
            )
        invoices, changes = [], []
        for index in range(count):
            offset, shape = _SHAPES[index % len(_SHAPES)]
            number = f"SAMPLE-{index + 1:04d}"
            gross = (40 + (index * 37) % 460) * 10000
            invoice_id = uuid.uuid4()
            invoices.append(
                {
                    "workspace_id": ctx.workspace_id,
                    "id": invoice_id,
                    "client_id": clients[index % len(clients)],
                    "external_id": number,
                    "invoice_number": number,
                    "normalized_number": normalize_number(number),
                    "issue_date": today + timedelta(days=offset - 30),
                    "due_date": today + timedelta(days=offset),
                    "currency": "INR",
                    "gross_minor": gross,
                }  # fmt: skip
            )
            changes.append((invoice_id, gross, shape))
        execute_many(
            "INSERT INTO invoices (workspace_id, id, client_id, source_system, external_id, invoice_number,"
            " normalized_number, issue_date, due_date, currency, gross_minor)"
            " VALUES (%(workspace_id)s, %(id)s, %(client_id)s, 'SAMPLE', %(external_id)s, %(invoice_number)s,"
            " %(normalized_number)s, %(issue_date)s, %(due_date)s, %(currency)s, %(gross_minor)s)",
            invoices,
        )
        create_states(invoices)
        for invoice_id, gross, shape in changes:
            self._shape(today, invoice_id, gross, shape)

    @staticmethod
    def _shape(today: date, invoice_id: uuid.UUID, gross: int, shape: dict[str, Any]) -> None:
        if not shape:
            return
        paid = gross * shape.get("paid_percent", 0) // 100
        snooze = today + timedelta(days=shape["snooze_days"]) if "snooze_days" in shape else None
        execute(
            "UPDATE invoice_state SET payment_status = COALESCE(%s, payment_status),"
            " dispute_status = COALESCE(%s, dispute_status), reminder_status = COALESCE(%s, reminder_status),"
            " paid_minor = %s, outstanding_minor = %s, snooze_until = %s WHERE invoice_id = %s",
            [
                shape.get("payment_status"),
                shape.get("dispute_status"),
                shape.get("reminder_status"),
                paid,
                gross - paid,
                snooze,
                invoice_id,
            ],  # fmt: skip
        )
