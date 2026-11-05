"""The ledger (SAD 6.6, TSD 9). Allocations are added or reversed, never rewritten.

The service checks everything first so a person gets a useful answer. These triggers are the backstop for
any other path: they take the same row locks, so two commits on one transaction or invoice take turns and
the later one sees the earlier one's rows. READ COMMITTED gives each statement in the function a new
snapshot, which is what makes the sums after the locks correct.

The transaction row is locked FOR NO KEY UPDATE and not FOR UPDATE. Each allocation's foreign key already
holds FOR KEY SHARE on that row, so FOR UPDATE would make two inserters wait on each other at commit.
"""

from django.db import migrations

from collectiq.platform.rls import enable_rls

CREATE = """
ALTER TABLE payment_transactions DROP CONSTRAINT payment_transactions_source_type_check;
ALTER TABLE payment_transactions ADD CONSTRAINT payment_transactions_source_type_check
    CHECK (source_type IN ('BANK_CSV', 'UPI_CSV', 'CASH_LOG', 'MANUAL'));
ALTER TABLE payment_transactions DROP CONSTRAINT payment_transactions_evidence_type_check;
ALTER TABLE payment_transactions ADD CONSTRAINT payment_transactions_evidence_type_check
    CHECK (evidence_type IN ('STATEMENT_ROW', 'USER_CONFIRMATION'));
ALTER TABLE payment_transactions ALTER COLUMN payment_account_id DROP NOT NULL;
ALTER TABLE payment_transactions ADD COLUMN method text
    CHECK (method IN ('BANK_TRANSFER', 'UPI', 'CASH', 'PAYPAL_MANUAL', 'OTHER'));
ALTER TABLE payment_transactions ADD COLUMN notes text;
ALTER TABLE payment_transactions ADD COLUMN void_reason text;
ALTER TABLE payment_transactions ADD CONSTRAINT payment_transactions_source_shape CHECK (
    (source_type = 'MANUAL' AND method IS NOT NULL AND evidence_type = 'USER_CONFIRMATION')
    OR (source_type <> 'MANUAL' AND payment_account_id IS NOT NULL AND method IS NULL
        AND evidence_type = 'STATEMENT_ROW')
);
ALTER TABLE payment_transactions ADD CONSTRAINT payment_transactions_void_has_reason
    CHECK (status <> 'VOID' OR void_reason IS NOT NULL);

CREATE TABLE payment_allocations (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id uuid NOT NULL,
    transaction_id uuid NOT NULL,
    invoice_id uuid NOT NULL,
    amount_minor bigint NOT NULL,
    currency text NOT NULL CHECK (currency ~ '^[A-Z]{3}$'),
    kind text NOT NULL CHECK (kind IN ('ALLOCATION', 'REVERSAL')),
    reverses_allocation_id uuid,
    match_id uuid,
    overpayment_confirmed boolean NOT NULL DEFAULT false,
    evidence_type text NOT NULL CHECK (evidence_type IN ('STATEMENT_ROW', 'USER_CONFIRMATION')),
    confirmed_by uuid NOT NULL,
    note text,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (workspace_id, id),
    CONSTRAINT payment_allocations_shape CHECK (
        (kind = 'ALLOCATION' AND amount_minor > 0 AND reverses_allocation_id IS NULL)
        OR (kind = 'REVERSAL' AND amount_minor < 0 AND reverses_allocation_id IS NOT NULL)
    ),
    CONSTRAINT payment_allocations_reversal_has_note
        CHECK (kind = 'ALLOCATION' OR (note IS NOT NULL AND btrim(note) <> '')),
    FOREIGN KEY (workspace_id, transaction_id) REFERENCES payment_transactions (workspace_id, id),
    FOREIGN KEY (workspace_id, invoice_id) REFERENCES invoices (workspace_id, id),
    FOREIGN KEY (workspace_id, reverses_allocation_id) REFERENCES payment_allocations (workspace_id, id),
    FOREIGN KEY (workspace_id, match_id) REFERENCES reconciliation_matches (workspace_id, id)
);
CREATE UNIQUE INDEX payment_allocations_one_reversal
    ON payment_allocations (workspace_id, reverses_allocation_id) WHERE kind = 'REVERSAL';
CREATE INDEX payment_allocations_transaction ON payment_allocations (workspace_id, transaction_id);
CREATE INDEX payment_allocations_invoice ON payment_allocations (workspace_id, invoice_id);

CREATE FUNCTION payment_allocations_append_only() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'payment_allocations is append-only: % is not allowed', TG_OP;
END $$;
CREATE TRIGGER payment_allocations_append_only BEFORE UPDATE OR DELETE ON payment_allocations
    FOR EACH ROW EXECUTE FUNCTION payment_allocations_append_only();

CREATE FUNCTION payment_allocations_invariants() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    trx record;
    inv record;
    original record;
    on_transaction bigint;
    on_invoice bigint;
BEGIN
    SELECT status, direction, amount_minor, currency, evidence_type INTO trx
      FROM payment_transactions
     WHERE workspace_id = NEW.workspace_id AND id = NEW.transaction_id
       FOR NO KEY UPDATE;
    PERFORM 1 FROM invoice_state
      WHERE workspace_id = NEW.workspace_id AND invoice_id = NEW.invoice_id
        FOR UPDATE;
    SELECT gross_minor, currency, status INTO inv
      FROM invoices WHERE workspace_id = NEW.workspace_id AND id = NEW.invoice_id;

    IF NEW.currency IS DISTINCT FROM trx.currency OR NEW.currency IS DISTINCT FROM inv.currency THEN
        RAISE EXCEPTION 'F-3: allocation %, transaction % and invoice % currencies differ',
            NEW.currency, trx.currency, inv.currency USING ERRCODE = 'check_violation';
    END IF;
    IF NEW.evidence_type IS DISTINCT FROM trx.evidence_type THEN
        RAISE EXCEPTION 'allocation evidence type % differs from its transaction %',
            NEW.evidence_type, trx.evidence_type USING ERRCODE = 'check_violation';
    END IF;

    IF NEW.kind = 'REVERSAL' THEN
        SELECT kind, transaction_id, invoice_id, amount_minor INTO original
          FROM payment_allocations
         WHERE workspace_id = NEW.workspace_id AND id = NEW.reverses_allocation_id;
        IF original.kind IS DISTINCT FROM 'ALLOCATION'
           OR original.transaction_id IS DISTINCT FROM NEW.transaction_id
           OR original.invoice_id IS DISTINCT FROM NEW.invoice_id
           OR -NEW.amount_minor > original.amount_minor THEN
            RAISE EXCEPTION 'F-4: a reversal must undo one allocation, on its own transaction and invoice,'
                ' by no more than its amount' USING ERRCODE = 'check_violation';
        END IF;
    ELSE
        IF trx.status IS DISTINCT FROM 'ACTIVE' OR trx.direction IS DISTINCT FROM 'CREDIT' THEN
            RAISE EXCEPTION 'allocation to a transaction that is not active money received'
                USING ERRCODE = 'check_violation';
        END IF;
        IF inv.status IS DISTINCT FROM 'ACTIVE' THEN
            RAISE EXCEPTION 'allocation to an invoice that is not active' USING ERRCODE = 'check_violation';
        END IF;
    END IF;

    SELECT COALESCE(sum(amount_minor), 0) INTO on_transaction FROM payment_allocations
     WHERE workspace_id = NEW.workspace_id AND transaction_id = NEW.transaction_id;
    IF on_transaction > trx.amount_minor OR on_transaction < 0 THEN
        RAISE EXCEPTION 'F-1: % allocated against a transaction of %', on_transaction, trx.amount_minor
            USING ERRCODE = 'check_violation';
    END IF;

    SELECT COALESCE(sum(amount_minor), 0) INTO on_invoice FROM payment_allocations
     WHERE workspace_id = NEW.workspace_id AND invoice_id = NEW.invoice_id;
    IF on_invoice < 0 THEN
        RAISE EXCEPTION 'F-2: % allocated against an invoice', on_invoice USING ERRCODE = 'check_violation';
    END IF;
    -- Deferred, so every row of a commit is already visible here. Past the total, some live allocation on the
    -- invoice must carry the confirmation. The service is stricter: each line going over needs its own flag.
    IF NEW.kind = 'ALLOCATION' AND on_invoice > inv.gross_minor AND NOT EXISTS (
        SELECT 1 FROM payment_allocations a
         WHERE a.workspace_id = NEW.workspace_id AND a.invoice_id = NEW.invoice_id
           AND a.kind = 'ALLOCATION' AND a.overpayment_confirmed
           AND NOT EXISTS (SELECT 1 FROM payment_allocations r
                            WHERE r.workspace_id = a.workspace_id AND r.reverses_allocation_id = a.id)
    ) THEN
        RAISE EXCEPTION 'F-2: % allocated against an invoice of % without confirming the overpayment',
            on_invoice, inv.gross_minor USING ERRCODE = 'check_violation';
    END IF;
    RETURN NULL;
END $$;
CREATE CONSTRAINT TRIGGER payment_allocations_invariants AFTER INSERT ON payment_allocations
    DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION payment_allocations_invariants();

CREATE FUNCTION payment_transactions_status_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.status <> 'ACTIVE' AND COALESCE(
        (SELECT sum(amount_minor) FROM payment_allocations
          WHERE workspace_id = NEW.workspace_id AND transaction_id = NEW.id), 0) <> 0 THEN
        RAISE EXCEPTION 'a transaction with live allocations cannot become %', NEW.status
            USING ERRCODE = 'check_violation';
    END IF;
    RETURN NULL;
END $$;
CREATE CONSTRAINT TRIGGER payment_transactions_status_guard AFTER UPDATE OF status ON payment_transactions
    DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION payment_transactions_status_guard();
"""

DROP = """
DROP TRIGGER payment_transactions_status_guard ON payment_transactions;
DROP FUNCTION payment_transactions_status_guard();
DROP TABLE payment_allocations;
DROP FUNCTION payment_allocations_invariants();
DROP FUNCTION payment_allocations_append_only();
DELETE FROM payment_transactions WHERE source_type = 'MANUAL';
ALTER TABLE payment_transactions DROP CONSTRAINT payment_transactions_void_has_reason;
ALTER TABLE payment_transactions DROP CONSTRAINT payment_transactions_source_shape;
ALTER TABLE payment_transactions DROP COLUMN void_reason;
ALTER TABLE payment_transactions DROP COLUMN notes;
ALTER TABLE payment_transactions DROP COLUMN method;
ALTER TABLE payment_transactions ALTER COLUMN payment_account_id SET NOT NULL;
ALTER TABLE payment_transactions DROP CONSTRAINT payment_transactions_evidence_type_check;
ALTER TABLE payment_transactions ADD CONSTRAINT payment_transactions_evidence_type_check
    CHECK (evidence_type IN ('STATEMENT_ROW'));
ALTER TABLE payment_transactions DROP CONSTRAINT payment_transactions_source_type_check;
ALTER TABLE payment_transactions ADD CONSTRAINT payment_transactions_source_type_check
    CHECK (source_type IN ('BANK_CSV', 'UPI_CSV', 'CASH_LOG'));
"""

# F-5: the app role may read and add. Nothing it holds lets it change or remove a ledger row.
PRIVILEGES = """
REVOKE UPDATE, DELETE, TRUNCATE ON payment_allocations FROM collectiq_app;
GRANT UPDATE (void_reason) ON payment_transactions TO collectiq_app;
"""


class Migration(migrations.Migration):
    dependencies = [("evidence", "0003_matches"), ("invoices", "0003_invoice_state")]
    operations = [
        migrations.RunSQL(CREATE, reverse_sql=DROP),
        enable_rls("payment_allocations"),
        migrations.RunSQL(PRIVILEGES, reverse_sql=migrations.RunSQL.noop),
    ]
