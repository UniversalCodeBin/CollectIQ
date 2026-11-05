"""The derived row each invoice has from the moment it exists.

`invoices` sits below `evidence` in the layers, so it owns only the initial row and the figure that
follows the invoice's own total. Deriving payment status from evidence is `evidence`'s job.
"""

from collections.abc import Iterable
from typing import Any
from uuid import UUID

from collectiq.platform.db import execute, execute_many


def create_states(rows: Iterable[dict[str, Any]]) -> None:
    """`rows` carry workspace_id, id and gross_minor. Runs in the caller's transaction."""
    execute_many(
        """
        INSERT INTO invoice_state (workspace_id, invoice_id, outstanding_minor)
        VALUES (%(workspace_id)s, %(id)s, %(gross_minor)s)
        """,
        list(rows),
    )


def refresh_after_total_changed(invoice_id: UUID | str) -> None:
    """The total moved. What was received stays as it is; what is owed follows."""
    execute(
        """
        UPDATE invoice_state s
           SET outstanding_minor = GREATEST(i.gross_minor - s.paid_minor, 0),
               overpayment_flag = s.paid_minor > i.gross_minor,
               version = s.version + 1,
               updated_at = now()
          FROM invoices i
         WHERE i.id = s.invoice_id AND i.workspace_id = s.workspace_id AND s.invoice_id = %s
        """,
        [invoice_id],
    )
