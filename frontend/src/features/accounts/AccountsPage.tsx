// FILE GUIDE: payment accounts (SCR-15, E060–E066). The accounts customers pay into, how far their statements reach,
// and whether that is recent enough to rely on (SUPPORTED / STALE / MISSING from evidence/domain/coverage.py).
// A statement is checked first (dry run) and only added when the person confirms. Confirming "no other payments" is a
// person's statement about the account, recorded as an attestation; it never marks any invoice paid.
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { type FormEvent, useEffect, useState } from "react";
import { useParams } from "react-router";
import { Button, ButtonLink } from "../../components/ui/Button";
import { Callout } from "../../components/ui/Callout";
import { Dialog } from "../../components/ui/Dialog";
import { EmptyState } from "../../components/ui/EmptyState";
import { fieldError, SelectField, TextField } from "../../components/ui/Field";
import { MutationFeedback } from "../../components/ui/MutationFeedback";
import { Page, PageHeader } from "../../components/ui/Page";
import { ProblemMessage } from "../../components/ui/ProblemMessage";
import { QueryState } from "../../components/ui/QueryState";
import { ApiProblem, apiRequest, useApiMutation } from "../../lib/api";
import type { components } from "../../lib/api-types";
import { formatDate } from "../../lib/format";
import styles from "./Accounts.module.css";

type Account = components["schemas"]["PaymentAccountSummaryOut"];

const KINDS: { value: string; text: string }[] = [
  { value: "BANK", text: "Bank account" },
  { value: "PAYPAL", text: "PayPal" },
  { value: "UPI", text: "UPI" },
  { value: "CASH", text: "Cash" },
];
const KIND_TEXT = Object.fromEntries(KINDS.map((k) => [k.value, k.text]));

const COVERAGE_TEXT: Record<string, string> = {
  SUPPORTED: "Up to date",
  STALE: "Out of date",
  MISSING: "No coverage yet",
};

const DATE_FORMATS = ["YYYY-MM-DD", "DD/MM/YYYY", "MM/DD/YYYY", "DD-MM-YYYY", "MM-DD-YYYY", "DD.MM.YYYY", "YYYY/MM/DD"];

const refuse = (field: string, message: string) =>
  new ApiProblem({
    status: 400,
    code: "VALIDATION_FAILED",
    detail: "",
    correlationId: null,
    errors: [{ field, message }],
  });
const isCsv = (file: File) => /\.csv$/i.test(file.name);

function When({ at }: { at: string }) {
  return (
    <time className={styles.date} dateTime={at}>
      {formatDate(at)}
    </time>
  );
}

/** Refreshes the account list and closes the dialog once the server has confirmed the change. */
function useRefresh(status: string, onDone: () => void) {
  const client = useQueryClient();
  useEffect(() => {
    if (status === "success") {
      void client.invalidateQueries({ queryKey: ["accounts"] });
      onDone();
    }
  }, [status, client, onDone]);
}

function DeclareDialog({ workspace, onClose }: { workspace: string; onClose: () => void }) {
  const create = useApiMutation(
    { method: "post", path: "/api/v1/workspaces/{ws}/payment-accounts" },
    { idempotent: true },
  );
  const [kind, setKind] = useState("BANK");
  const [label, setLabel] = useState("");
  const [currency, setCurrency] = useState("INR");
  const [local, setLocal] = useState<ApiProblem | null>(null);
  const pending = create.status === "pending";

  useRefresh(create.status, onClose);

  function submit(event: FormEvent) {
    event.preventDefault();
    if (pending) return;
    if (!label.trim()) return setLocal(refuse("label", "Give the account a name."));
    setLocal(null);
    create.submit({
      path: { ws: workspace },
      body: { kind: kind as never, label: label.trim(), currency: currency as never },
    });
  }

  return (
    <Dialog open onClose={onClose} title="Declare an account">
      <form className={styles.form} onSubmit={submit} noValidate>
        <SelectField label="Kind" value={kind} onChange={(e) => setKind(e.target.value)}>
          {KINDS.map((k) => (
            <option key={k.value} value={k.value}>
              {k.text}
            </option>
          ))}
        </SelectField>
        <TextField
          label="Account name"
          hint="The name your team knows it by, such as the bank and account type."
          value={label}
          onChange={(e) => setLabel(e.target.value)}
          error={fieldError(local, "label")}
        />
        <SelectField label="Currency" value={currency} onChange={(e) => setCurrency(e.target.value)}>
          {["INR", "USD", "EUR", "GBP"].map((c) => (
            <option key={c}>{c}</option>
          ))}
        </SelectField>
        <MutationFeedback mutation={create} />
        <div className={styles.actions}>
          <Button variant="primary" type="submit" busy={pending} aria-disabled={pending || undefined}>
            Save account
          </Button>
          <Button data-cancel onClick={onClose}>
            Cancel
          </Button>
        </div>
      </form>
    </Dialog>
  );
}

type Preview = { added: number; held: number; invalid: { row: number; message: string }[] };

function StatementDialog({
  workspace,
  account,
  onClose,
}: {
  workspace: string;
  account: Account;
  onClose: () => void;
}) {
  const client = useQueryClient();
  const [file, setFile] = useState<File | null>(null);
  const [dateCol, setDateCol] = useState("Date");
  const [descCol, setDescCol] = useState("Description");
  const [amountCol, setAmountCol] = useState("Amount");
  const [dateFormat, setDateFormat] = useState("");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [problem, setProblem] = useState<ApiProblem | null>(null);
  const [preview, setPreview] = useState<Preview | null>(null);
  const [busy, setBusy] = useState(false);

  /** Any change to the file or how it is read voids an earlier check, so nothing unchecked is added. */
  const change =
    <T,>(set: (value: T) => void) =>
    (value: T) => {
      set(value);
      setPreview(null);
    };

  async function send(dry: boolean) {
    if (busy) return;
    if (!file) return setProblem(refuse("file", "Choose a CSV file to upload."));
    if (!isCsv(file)) return setProblem(refuse("file", "Choose a CSV file. Other kinds of file can't be imported."));
    if (!dateFormat)
      return setProblem(refuse("date_format", "Choose how dates are written in this file. Dates are never guessed."));
    if (!from || !to)
      return setProblem(refuse("coverage_from", "Confirm the first and last date this statement covers."));
    setProblem(null);
    setBusy(true);
    const body = new FormData();
    body.set("file", file);
    body.set("source_type", "BANK_CSV");
    body.set("payment_account_id", account.id);
    body.set("mapping", JSON.stringify({ date: dateCol, description: descCol, amount: amountCol }));
    body.set("date_format", dateFormat);
    body.set("coverage_from", from);
    body.set("coverage_to", to);
    body.set("dry_run", String(dry));
    try {
      const result = await apiRequest(
        { method: "post", path: "/api/v1/workspaces/{ws}/imports/transactions" },
        { path: { ws: workspace }, body } as never,
        { idempotencyKey: crypto.randomUUID() },
      );
      if (dry)
        setPreview({
          added: result.counts.added,
          held: result.counts.held_for_confirmation,
          invalid: ((result as { errors?: { row: number; message: string }[] }).errors ?? []).slice(0, 5),
        });
      else {
        void client.invalidateQueries({ queryKey: ["accounts"] });
        void client.invalidateQueries({ queryKey: ["reconciliation"] });
        onClose();
      }
    } catch (error) {
      setProblem(
        error instanceof ApiProblem
          ? error
          : new ApiProblem({ status: 0, code: "NETWORK", detail: "", correlationId: null }),
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog open onClose={onClose} title="Upload statement">
      <div className={styles.form}>
        <p className={styles.muted}>
          For <strong className={styles.strong}>{account.label}</strong>. CollectIQ checks the file first and shows what
          it found before anything is added.
        </p>
        <TextField
          label="Statement file"
          type="file"
          accept=".csv,text/csv"
          hint="A CSV export from your bank."
          onChange={(e) => change(setFile)(e.target.files?.[0] ?? null)}
        />
        <fieldset className={styles.fieldset}>
          <legend className={styles.legend}>Column names in your file</legend>
          <div className={styles.columns}>
            <TextField label="Date column" value={dateCol} onChange={(e) => change(setDateCol)(e.target.value)} />
            <TextField
              label="Description column"
              value={descCol}
              onChange={(e) => change(setDescCol)(e.target.value)}
            />
            <TextField label="Amount column" value={amountCol} onChange={(e) => change(setAmountCol)(e.target.value)} />
          </div>
        </fieldset>
        <SelectField
          label="Date format"
          value={dateFormat}
          onChange={(e) => change(setDateFormat)(e.target.value)}
          error={fieldError(problem, "date_format")}
        >
          <option value="">Choose a date format</option>
          {DATE_FORMATS.map((f) => (
            <option key={f}>{f}</option>
          ))}
        </SelectField>
        <fieldset className={styles.fieldset}>
          <legend className={styles.legend}>Dates this statement covers</legend>
          <div className={styles.columns}>
            <TextField
              label="Statement covers from"
              type="date"
              value={from}
              onChange={(e) => change(setFrom)(e.target.value)}
            />
            <TextField
              label="Statement covers to"
              type="date"
              value={to}
              onChange={(e) => change(setTo)(e.target.value)}
            />
          </div>
        </fieldset>
        {preview && (
          <Callout role="status" title="Checked">
            {preview.added === 1 ? "1 transaction" : `${preview.added} transactions`} will be added
            {preview.held ? `, ${preview.held} held for your confirmation` : ""}. Nothing is added until you confirm.
          </Callout>
        )}
        {preview && preview.invalid.length > 0 && (
          <ul aria-label="Rows that cannot be read" className={styles.invalidList}>
            {preview.invalid.map((e) => (
              <li key={e.row}>{`Row ${e.row}: ${e.message}`}</li>
            ))}
          </ul>
        )}
        {problem && <ProblemMessage problem={problem} />}
        <div className={styles.actions}>
          {preview ? (
            <Button variant="primary" busy={busy} aria-disabled={busy || undefined} onClick={() => void send(false)}>
              Add transactions
            </Button>
          ) : (
            <Button variant="primary" busy={busy} aria-disabled={busy || undefined} onClick={() => void send(true)}>
              Check statement
            </Button>
          )}
          <Button data-cancel onClick={onClose}>
            Cancel
          </Button>
        </div>
      </div>
    </Dialog>
  );
}

function AttestDialog({ workspace, account, onClose }: { workspace: string; account: Account; onClose: () => void }) {
  const attest = useApiMutation({ method: "post", path: "/api/v1/workspaces/{ws}/attestations" }, { idempotent: true });
  const [note, setNote] = useState("");
  const pending = attest.status === "pending";
  useRefresh(attest.status, onClose);

  return (
    <Dialog open onClose={onClose} title="Confirm no other payments">
      <div className={styles.form}>
        <Callout>
          You are saying that, as of now, you know of no payments into <strong>{account.label}</strong> that are missing
          from CollectIQ. This is recorded under your name. It keeps the account up to date for a limited time, after
          which it shows as out of date again. It does not mark any invoice paid.
        </Callout>
        <TextField label="Note (optional)" value={note} onChange={(e) => setNote(e.target.value)} />
        <MutationFeedback mutation={attest} />
        <div className={styles.actions}>
          <Button
            variant="primary"
            busy={pending}
            aria-disabled={pending || undefined}
            onClick={() =>
              !pending &&
              attest.submit({
                path: { ws: workspace },
                body: {
                  scope: "ACCOUNT",
                  account_id: account.id,
                  as_of: new Date().toISOString(),
                  ...(note.trim() ? { note: note.trim() } : {}),
                },
              })
            }
          >
            Confirm
          </Button>
          <Button data-cancel onClick={onClose}>
            Cancel
          </Button>
        </div>
      </div>
    </Dialog>
  );
}

function AccountRow({
  account: a,
  onUpload,
  onAttest,
}: {
  account: Account;
  onUpload: () => void;
  onAttest: () => void;
}) {
  const gaps = (a.gaps as { from?: string; to?: string }[]).filter((g) => g.from && g.to);
  return (
    <li className={styles.account}>
      <div className={styles.head}>
        <div className={styles.name}>
          <h2 className={styles.label}>{a.label}</h2>
          <p className={styles.kind}>
            {KIND_TEXT[a.kind] ?? a.kind}, {a.currency}
            {a.status === "INACTIVE" && <span className={styles.inactive}>Inactive</span>}
          </p>
        </div>
        <span className={styles.coverage} data-coverage={a.coverage_status}>
          {COVERAGE_TEXT[a.coverage_status] ?? a.coverage_status}
        </span>
      </div>

      <div className={styles.facts}>
        <p>
          {a.statements_through ? (
            <>
              Statements through <When at={a.statements_through} />
            </>
          ) : (
            "No statement uploaded yet"
          )}
        </p>
        {a.attested_through && (
          <p>
            No other payments confirmed through <When at={a.attested_through} />
          </p>
        )}
        {gaps.length > 0 && (
          <div className={styles.gaps}>
            <p>No statement covers these days, so statements after them do not count yet:</p>
            <ul>
              {gaps.map((g) => (
                <li key={`${g.from}-${g.to}`}>
                  <When at={g.from!} /> to <When at={g.to!} />
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>

      <div className={styles.actions}>
        <Button variant="secondary" size="sm" onClick={onUpload}>
          Upload statement
        </Button>
        <Button variant="quiet" size="sm" onClick={onAttest}>
          Confirm no other payments
        </Button>
      </div>
    </li>
  );
}

export function AccountsPage() {
  const { ws = "" } = useParams();
  const [declaring, setDeclaring] = useState(false);
  const [uploading, setUploading] = useState<Account | null>(null);
  const [attesting, setAttesting] = useState<Account | null>(null);

  const list = useQuery({
    queryKey: ["accounts", ws],
    queryFn: () => apiRequest({ method: "get", path: "/api/v1/workspaces/{ws}/payment-accounts" }, { path: { ws } }),
  });
  const items = list.data?.items ?? [];

  return (
    <Page>
      <PageHeader
        title="Payment Accounts"
        description="The accounts customers pay into. Upload their statements so payments can be matched to invoices. An account counts as up to date only while its latest statement, or your confirmation, is recent."
        actions={
          <>
            <ButtonLink to={`/w/${ws}/reconciliation/confirmed`} variant="quiet">
              View Transactions
            </ButtonLink>
            <Button variant="primary" onClick={() => setDeclaring(true)}>
              Declare an account
            </Button>
          </>
        }
      />

      <QueryState query={list} label="accounts">
        {list.data && items.length === 0 ? (
          <EmptyState
            title="No accounts yet"
            body="Declare the accounts where customers pay you, so statements can be matched to invoices."
          />
        ) : (
          <ul className={styles.list}>
            {items.map((a) => (
              <AccountRow key={a.id} account={a} onUpload={() => setUploading(a)} onAttest={() => setAttesting(a)} />
            ))}
          </ul>
        )}
      </QueryState>

      {declaring && <DeclareDialog workspace={ws} onClose={() => setDeclaring(false)} />}
      {uploading && <StatementDialog workspace={ws} account={uploading} onClose={() => setUploading(null)} />}
      {attesting && <AttestDialog workspace={ws} account={attesting} onClose={() => setAttesting(null)} />}
    </Page>
  );
}
