"""Match proposals (E055, E056). Nothing here allocates money or changes a balance (BR-12).

A proposal only moves an invoice to AWAITING_VERIFICATION or UNCERTAIN, through `service_state`, so a
person decides before any reminder resumes. A rejected pair is not proposed again unless its inputs change.
"""

import hashlib
import json
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import replace
from typing import Any
from uuid import UUID

from collectiq.audit import record
from collectiq.platform import outbox
from collectiq.platform.context import RequestContext
from collectiq.platform.db import execute, fetch_all, fetch_one, tenant_tx
from collectiq.platform.errors import ProblemError
from collectiq.tenancy.permissions import LEDGER_WRITE, authorize

from . import service_state
from .domain.matcher import MATCHER_VERSION, Candidate, MatchResult, Txn, match

TRANSACTIONS_IMPORTED = "TransactionsImported"
ALLOCATION_REVERSED = "AllocationReversed"
BAND_LABELS = {"HIGH": "Strong", "MEDIUM": "Possible", "LOW": "Weak"}
_OPEN_STATES = ("OUTSTANDING", "PARTIALLY_PAID", "AWAITING_VERIFICATION", "UNCERTAIN")


def _inputs_hash(txn: dict[str, Any], inv: dict[str, Any]) -> str:
    parts = [
        MATCHER_VERSION,
        txn["amount_minor"],
        txn["currency"],
        txn["value_date"],
        sorted(txn["reference_candidates"] or []),
        txn["payer_descriptor"] or "",
        inv["normalized_number"],
        inv["gross_minor"],
        inv["outstanding_minor"],
        inv["issue_date"],
        inv["due_date"],
        inv["currency"],
    ]
    return hashlib.sha256(json.dumps(parts, default=str).encode()).hexdigest()


def _candidates(currency: str) -> tuple[list[dict[str, Any]], list[Candidate]]:
    rows = fetch_all(
        "SELECT i.id, i.client_id, i.normalized_number, i.currency, i.gross_minor, s.outstanding_minor,"
        "       i.issue_date, i.due_date"
        "  FROM invoices i JOIN invoice_state s ON s.invoice_id = i.id AND s.workspace_id = i.workspace_id"
        " WHERE i.status = 'ACTIVE' AND i.currency = %s AND s.outstanding_minor > 0"
        "   AND s.payment_status = ANY(%s)",
        [currency, list(_OPEN_STATES)],
    )
    aliases: dict[Any, list[str]] = defaultdict(list)
    for a in fetch_all("SELECT client_id, text FROM client_aliases WHERE kind = 'NAME'"):
        aliases[a["client_id"]].append(a["text"])
    candidates = [
        Candidate(
            id=str(r["id"]),
            normalized_number=r["normalized_number"],
            currency=r["currency"],
            gross_minor=r["gross_minor"],
            outstanding_minor=r["outstanding_minor"],
            issue_date=r["issue_date"],
            due_date=r["due_date"],
            aliases=tuple(aliases.get(r["client_id"], ())),
        )
        for r in rows
    ]
    return rows, candidates


def _history_rows(client_id: Any) -> list[dict[str, Any]]:
    """The payers and accounts behind this client's allocations that still stand (one query per client).

    A person's own E059 choice teaches and a reversal unteaches, because only unreversed allocations count.
    """
    return fetch_all(
        "SELECT t.payer_descriptor, t.payment_account_id FROM payment_allocations a"
        "  JOIN payment_transactions t ON t.id = a.transaction_id AND t.workspace_id = a.workspace_id"
        "  JOIN invoices i ON i.id = a.invoice_id AND i.workspace_id = a.workspace_id"
        " WHERE a.kind = 'ALLOCATION' AND i.client_id = %s"
        "   AND NOT EXISTS (SELECT 1 FROM payment_allocations r WHERE r.reverses_allocation_id = a.id)",
        [client_id],
    )


def _history(
    txn: dict[str, Any], client_id: Any, known: dict[Any, list[dict[str, Any]]]
) -> tuple[bool, bool]:
    """(same payer confirmed for this client before, this account paid this client before).

    `known` holds each client's rows for the length of one reconcile run, so a pool of candidates costs
    one query per client, not one per candidate per payment.
    """
    if client_id not in known:
        known[client_id] = _history_rows(client_id)
    rows = known[client_id]
    payer = (txn["payer_descriptor"] or "").casefold()
    return (
        any(payer and (r["payer_descriptor"] or "").casefold() == payer for r in rows),
        any(r["payment_account_id"] == txn["payment_account_id"] for r in rows),
    )


def _factors(raw: object) -> list[dict[str, object]]:
    loaded: Any = json.loads(raw) if isinstance(raw, str) else raw
    return list(loaded or [])


def _factor_json(result: MatchResult) -> str:
    return json.dumps([{"code": f.code, "text": f.text, "points": f.points} for f in result.factors])


def reconcile(ctx: RequestContext, transaction_ids: Sequence[UUID | str]) -> int:
    """Propose matches for statement credits with money left. Runs in the caller's transaction.

    Returns proposals made. Locks each transaction row first, the same order as allocation. Manual entries
    are never proposed: a person entered them, and a person chooses their invoices.
    """
    txns = fetch_all(
        "SELECT id, payment_account_id, amount_minor, currency, value_date, reference_candidates,"
        "       payer_descriptor FROM payment_transactions"
        " WHERE id = ANY(%s::uuid[]) AND direction = 'CREDIT' AND status = 'ACTIVE'"
        "   AND source_type <> 'MANUAL'"
        "   AND amount_minor > (SELECT COALESCE(sum(a.amount_minor), 0) FROM payment_allocations a"
        "                        WHERE a.transaction_id = payment_transactions.id)"
        " ORDER BY id FOR NO KEY UPDATE",
        [list(transaction_ids)],
    )
    pool: dict[str, tuple[list[dict[str, Any]], list[Candidate]]] = {}
    touched: set[str] = set()
    learned: dict[Any, list[dict[str, Any]]] = {}
    made = 0
    for t in txns:
        rows, candidates = pool.setdefault(t["currency"], _candidates(t["currency"]))
        by_id = {str(r["id"]): r for r in rows}
        enriched = []
        for c in candidates:
            row = by_id[c.id]
            confirmed, history = _history(t, row["client_id"], learned)
            enriched.append(replace(c, alias_confirmed=confirmed, account_history=history))
        results = match(
            Txn(
                str(t["id"]),
                t["amount_minor"],
                t["currency"],
                t["value_date"],
                tuple(t["reference_candidates"] or ()),
                t["payer_descriptor"],
            ),
            enriched,
        )
        old = fetch_all(
            "SELECT id, invoice_id, inputs_hash, status FROM reconciliation_matches"
            " WHERE transaction_id = %s AND status IN ('PROPOSED', 'REJECTED', 'CONFIRMED')",
            [t["id"]],
        )
        rejected = {(str(o["invoice_id"]), o["inputs_hash"]) for o in old if o["status"] == "REJECTED"}
        settled = {str(o["invoice_id"]) for o in old if o["status"] == "CONFIRMED"}
        keep: set[str] = set()
        for r in results:
            digest = _inputs_hash(t, by_id[r.invoice_id])
            if (r.invoice_id, digest) in rejected or r.invoice_id in settled:
                continue
            same = next(
                (
                    o
                    for o in old
                    if o["status"] == "PROPOSED"
                    and str(o["invoice_id"]) == r.invoice_id
                    and o["inputs_hash"] == digest
                ),
                None,
            )
            if same:
                keep.add(str(same["id"]))
                continue
            for o in old:
                if o["status"] == "PROPOSED" and str(o["invoice_id"]) == r.invoice_id:
                    _supersede(o["id"])
                    touched.add(r.invoice_id)
            created = fetch_one(
                "INSERT INTO reconciliation_matches (workspace_id, transaction_id, invoice_id, band, score,"
                " ambiguous, factors, matcher_version, inputs_hash)"
                " VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s) RETURNING id",
                [
                    ctx.workspace_id,
                    t["id"],
                    r.invoice_id,
                    r.band,
                    r.score,
                    r.ambiguous,
                    _factor_json(r),
                    MATCHER_VERSION,
                    digest,
                ],
            )
            assert created is not None
            keep.add(str(created["id"]))
            touched.add(r.invoice_id)
            made += 1
            record(
                ctx,
                "match.proposed",
                "reconciliation_match",
                str(created["id"]),
                after={
                    "transaction_id": str(t["id"]),
                    "invoice_id": r.invoice_id,
                    "band": r.band,
                    "ambiguous": r.ambiguous,
                    "factors": [f.code for f in r.factors],
                    "matcher_version": MATCHER_VERSION,
                },
                reason_codes=["MATCH_PROPOSED"],
            )
        for o in old:
            if o["status"] == "PROPOSED" and str(o["id"]) not in keep:
                _supersede(o["id"])
                touched.add(str(o["invoice_id"]))
    # the invoices on the other side of a changed ambiguity must follow too
    for invoice_id in sorted(touched):
        service_state.recompute(ctx, invoice_id)
    return made


def _supersede(match_id: Any) -> None:
    execute(
        "UPDATE reconciliation_matches SET status = 'SUPERSEDED', decided_at = now() WHERE id = %s",
        [match_id],
    )


def reject(ctx: RequestContext, match_id: UUID, reason: str | None = None) -> dict[str, Any]:
    """A person declines a proposal. It is remembered with the inputs it was made on (BR-15)."""
    authorize(ctx, LEDGER_WRITE)
    with tenant_tx(ctx):
        found = fetch_one(
            "SELECT id, invoice_id, transaction_id FROM reconciliation_matches WHERE id = %s", [match_id]
        )
        if found is None:
            raise ProblemError("NOT_FOUND", 404, "That proposal does not exist.")
        # the invoice first, the same order as allocation, and the status only after waiting for it
        fetch_one(
            "SELECT 1 AS locked FROM invoice_state WHERE invoice_id = %s FOR UPDATE", [found["invoice_id"]]
        )
        row = fetch_one("SELECT status FROM reconciliation_matches WHERE id = %s FOR UPDATE", [match_id])
        assert row is not None
        if row["status"] != "PROPOSED":
            raise ProblemError("STATE_TRANSITION_INVALID", 409, "That proposal has already been decided.")
        execute(
            "UPDATE reconciliation_matches SET status = 'REJECTED', decided_by = %s, decided_at = now(),"
            " decision_reason = %s WHERE id = %s",
            [ctx.user_id, reason, match_id],
        )
        record(
            ctx,
            "match.rejected",
            "reconciliation_match",
            str(match_id),
            after={
                "invoice_id": str(found["invoice_id"]),
                "transaction_id": str(found["transaction_id"]),
                "reason": reason,
            },
            reason_codes=["MATCH_REJECTED"],
        )
        service_state.recompute(ctx, found["invoice_id"])
        return {
            "id": str(match_id),
            "status": "REJECTED",
            "invoice_states": service_state.snapshot([found["invoice_id"]]),
        }


@outbox.subscriber(TRANSACTIONS_IMPORTED)
def _on_transactions_imported(ctx: RequestContext, payload: dict[str, Any]) -> None:
    ids = [
        r["id"]
        for r in fetch_all(
            "SELECT id FROM payment_transactions WHERE import_batch_id = %s AND direction = 'CREDIT'",
            [payload["batch_id"]],
        )
    ]
    if ids:
        reconcile(ctx, ids)


@outbox.subscriber(ALLOCATION_REVERSED)
def _on_allocation_reversed(ctx: RequestContext, payload: dict[str, Any]) -> None:
    """Money came back. Consider it again, and the rivals that were withdrawn when the invoice settled."""
    rivals = fetch_all(
        "SELECT DISTINCT transaction_id FROM reconciliation_matches"
        " WHERE invoice_id = %s AND status = 'SUPERSEDED'",
        [payload["invoice_id"]],
    )
    reconcile(ctx, sorted({payload["transaction_id"], *(str(r["transaction_id"]) for r in rivals)}))


# ---- reads ------------------------------------------------------------------------------------------


def list_unmatched(ctx: RequestContext, limit: int, cursor: UUID | None) -> dict[str, Any]:
    with tenant_tx(ctx):
        rows = fetch_all(
            "SELECT t.id, t.amount_minor, t.currency, t.value_date, t.reference, t.payer_descriptor,"
            "       t.source_type, a.label AS account_label, t.amount_minor - x.allocated AS remaining_minor,"
            "       (SELECT count(*) FROM reconciliation_matches m WHERE m.transaction_id = t.id"
            "           AND m.status = 'PROPOSED' AND m.band <> 'LOW') AS proposal_count"
            "  FROM payment_transactions t LEFT JOIN payment_accounts a"
            "    ON a.id = t.payment_account_id AND a.workspace_id = t.workspace_id"
            "  CROSS JOIN LATERAL (SELECT COALESCE(sum(pa.amount_minor), 0)::bigint AS allocated"
            "                        FROM payment_allocations pa WHERE pa.transaction_id = t.id) x"
            " WHERE t.direction = 'CREDIT' AND t.status = 'ACTIVE' AND t.amount_minor > x.allocated"
            "   AND (%(cursor)s::uuid IS NULL OR t.id > %(cursor)s::uuid) ORDER BY t.id LIMIT %(limit)s",
            {"cursor": cursor, "limit": limit + 1},
        )
    page = rows[:limit]
    return {
        "items": [{**r, "id": str(r["id"])} for r in page],
        "next_cursor": str(page[-1]["id"]) if len(rows) > limit else None,
    }


def list_proposals(ctx: RequestContext, limit: int, cursor: UUID | None) -> dict[str, Any]:
    with tenant_tx(ctx):
        rows = fetch_all(
            "SELECT m.id, m.band, m.ambiguous, m.factors, m.transaction_id, m.invoice_id,"
            "       t.amount_minor AS txn_amount_minor, t.currency AS txn_currency, t.value_date,"
            "       t.payer_descriptor, t.reference,"
            "       i.invoice_number, i.due_date, s.outstanding_minor, c.display_name AS client_name"
            "  FROM reconciliation_matches m"
            "  JOIN payment_transactions t ON t.id = m.transaction_id AND t.workspace_id = m.workspace_id"
            "  JOIN invoices i ON i.id = m.invoice_id AND i.workspace_id = m.workspace_id"
            "  JOIN invoice_state s ON s.invoice_id = i.id AND s.workspace_id = i.workspace_id"
            "  JOIN clients c ON c.id = i.client_id AND c.workspace_id = i.workspace_id"
            " WHERE m.status = 'PROPOSED'"
            "   AND (%(cursor)s::uuid IS NULL OR m.id > %(cursor)s::uuid) ORDER BY m.id LIMIT %(limit)s",
            {"cursor": cursor, "limit": limit + 1},
        )
    page = rows[:limit]
    items = [
        {
            "id": str(r["id"]),
            "label": BAND_LABELS[r["band"]],
            "ambiguous": r["ambiguous"],
            "reasons": [{"code": f["code"], "text": f["text"]} for f in _factors(r["factors"])],
            "transaction": {
                "id": str(r["transaction_id"]),
                "amount_minor": r["txn_amount_minor"],
                "currency": r["txn_currency"],
                "value_date": r["value_date"],
                "payer_descriptor": r["payer_descriptor"],
                "reference": r["reference"],
            },
            "invoice": {
                "id": str(r["invoice_id"]),
                "invoice_number": r["invoice_number"],
                "client_name": r["client_name"],
                "outstanding_minor": r["outstanding_minor"],
                "due_date": r["due_date"],
            },
        }
        for r in page
    ]
    return {"items": items, "next_cursor": str(page[-1]["id"]) if len(rows) > limit else None}
