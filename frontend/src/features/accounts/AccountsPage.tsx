import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useParams } from "react-router";
import { type FormEvent, useEffect, useState } from "react";
import { Button } from "../../components/ui/Button";
import { Dialog } from "../../components/ui/Dialog";
import { EmptyState } from "../../components/ui/EmptyState";
import { fieldError, SelectField, TextField } from "../../components/ui/Field";
import { MutationFeedback } from "../../components/ui/MutationFeedback";
import { ProblemMessage } from "../../components/ui/ProblemMessage";
import { QueryState } from "../../components/ui/QueryState";
import { ApiProblem, apiRequest, useApiMutation } from "../../lib/api";
import { formatDate } from "../../lib/format";
import styles from "./Accounts.module.css";

const refuse = (field: string, message: string) =>
  new ApiProblem({ status: 400, code: "VALIDATION_FAILED", detail: "", correlationId: null, errors: [{ field, message }] });
const isCsv = (file: File) => /\.csv$/i.test(file.name);

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
  const create = useApiMutation({ method: "post", path: "/api/v1/workspaces/{ws}/payment-accounts" }, { idempotent: true });
  const [kind, setKind] = useState("BANK");
  const [label, setLabel] = useState("");
  const [currency, setCurrency] = useState("INR");
  const [local, setLocal] = useState<ApiProblem | null>(null);
  useRefresh(create.status, onClose);
  function submit(event: FormEvent) {
    event.preventDefault();
    if (!label.trim()) return setLocal(refuse("label", "Give the account a name."));
    setLocal(null);
    create.submit({ path: { ws: workspace }, body: { kind: kind as never, label: label.trim(), currency: currency as never } });
  }
  return (
    <Dialog open onClose={onClose} title="Declare an account">
      <form className={styles.form} onSubmit={submit} noValidate>
        <SelectField label="Kind" value={kind} onChange={(e) => setKind(e.target.value)}>
          {["BANK", "PAYPAL", "UPI", "CASH"].map((k) => (
            <option key={k}>{k}</option>
          ))}
        </SelectField>
        <TextField label="Account name" value={label} onChange={(e) => setLabel(e.target.value)} error={fieldError(local, "label")} />
        <SelectField label="Currency" value={currency} onChange={(e) => setCurrency(e.target.value)}>
          {["INR", "USD", "EUR", "GBP"].map((c) => (
            <option key={c}>{c}</option>
          ))}
        </SelectField>
        <MutationFeedback mutation={create} />
        <div className={styles.actions}>
          <Button variant="primary" type="submit" aria-disabled={create.status === "pending" || undefined}>
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

function StatementDialog({ workspace, accountId, onClose }: { workspace: string; accountId: string; onClose: () => void }) {
  const client = useQueryClient();
  const [file, setFile] = useState<File | null>(null);
  const [dateCol, setDateCol] = useState("Date");
  const [descCol, setDescCol] = useState("Description");
  const [amountCol, setAmountCol] = useState("Amount");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [problem, setProblem] = useState<ApiProblem | null>(null);
  const [preview, setPreview] = useState<{ added: number; held: number } | null>(null);
  const [busy, setBusy] = useState(false);

  async function send(dry: boolean) {
    if (!file) return setProblem(refuse("file", "Choose a CSV file to upload."));
    if (!isCsv(file)) return setProblem(refuse("file", "Choose a CSV file. Other kinds of file can't be imported."));
    if (!from || !to) return setProblem(refuse("coverage_from", "Confirm the first and last date this statement covers."));
    setProblem(null);
    setBusy(true);
    const body = new FormData();
    body.set("file", file);
    body.set("source_type", "BANK_CSV");
    body.set("payment_account_id", accountId);
    body.set("mapping", JSON.stringify({ date: dateCol, description: descCol, amount: amountCol }));
    body.set("coverage_from", from);
    body.set("coverage_to", to);
    body.set("dry_run", String(dry));
    try {
      const result = await apiRequest({ method: "post", path: "/api/v1/workspaces/{ws}/imports/transactions" }, { path: { ws: workspace }, body } as never, {
        idempotencyKey: crypto.randomUUID(),
      });
      if (dry) setPreview({ added: result.counts.added, held: result.counts.held_for_confirmation });
      else {
        void client.invalidateQueries({ queryKey: ["accounts"] });
        void client.invalidateQueries({ queryKey: ["reconciliation"] });
        onClose();
      }
    } catch (error) {
      setProblem(error instanceof ApiProblem ? error : new ApiProblem({ status: 0, code: "NETWORK", detail: "", correlationId: null }));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog open onClose={onClose} title="Upload statement">
      <div className={styles.form}>
        <TextField label="Statement file" type="file" accept=".csv,text/csv" onChange={(e) => { setFile(e.target.files?.[0] ?? null); setPreview(null); }} />
        <TextField label="Date column" value={dateCol} onChange={(e) => setDateCol(e.target.value)} />
        <TextField label="Description column" value={descCol} onChange={(e) => setDescCol(e.target.value)} />
        <TextField label="Amount column" value={amountCol} onChange={(e) => setAmountCol(e.target.value)} />
        <TextField label="Statement covers from" type="date" value={from} onChange={(e) => setFrom(e.target.value)} />
        <TextField label="Statement covers to" type="date" value={to} onChange={(e) => setTo(e.target.value)} />
        {preview && (
          <p role="status">
            {preview.added} payments will be added{preview.held ? `, ${preview.held} held for your confirmation` : ""}. Nothing is added until you confirm.
          </p>
        )}
        {problem && <ProblemMessage problem={problem} />}
        <div className={styles.actions}>
          {preview ? (
            <Button variant="primary" aria-disabled={busy || undefined} onClick={() => void send(false)}>
              Add transactions
            </Button>
          ) : (
            <Button variant="primary" aria-disabled={busy || undefined} onClick={() => void send(true)}>
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

function AttestDialog({ workspace, accountId, onClose }: { workspace: string; accountId: string; onClose: () => void }) {
  const attest = useApiMutation({ method: "post", path: "/api/v1/workspaces/{ws}/attestations" }, { idempotent: true });
  const [note, setNote] = useState("");
  useRefresh(attest.status, onClose);
  return (
    <Dialog open onClose={onClose} title="Confirm no other payments">
      <div className={styles.form}>
        <p className={styles.muted}>
          You are saying that, as of now, you know of no payments to this account that are missing here. This counts for 7 days.
        </p>
        <TextField label="Note (optional)" value={note} onChange={(e) => setNote(e.target.value)} />
        <MutationFeedback mutation={attest} />
        <div className={styles.actions}>
          <Button
            variant="primary"
            aria-disabled={attest.status === "pending" || undefined}
            onClick={() =>
              attest.submit({
                path: { ws: workspace },
                body: { scope: "ACCOUNT", account_id: accountId, as_of: new Date().toISOString(), ...(note.trim() ? { note: note.trim() } : {}) },
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

export function AccountsPage() {
  const { ws = "" } = useParams();
  const [declaring, setDeclaring] = useState(false);
  const [uploading, setUploading] = useState<string | null>(null);
  const [attesting, setAttesting] = useState<string | null>(null);
  const list = useQuery({
    queryKey: ["accounts", ws],
    queryFn: () => apiRequest({ method: "get", path: "/api/v1/workspaces/{ws}/payment-accounts" }, { path: { ws } }),
  });
  return (
    <div className={styles.page}>
      <h1 className={styles.title}>Payment Accounts</h1>
      <div className={styles.toolbar}>
        <Button variant="primary" onClick={() => setDeclaring(true)}>
          Declare an account
        </Button>
      </div>
      <QueryState query={list} label="accounts">
        {(list.data?.items.length ?? 0) === 0 ? (
          <EmptyState title="No accounts yet" body="Declare the accounts where customers pay you, so statements can be matched to invoices." />
        ) : (
          <ul className={styles.list}>
            {list.data?.items.map((a) => (
              <li key={a.id} className={styles.card}>
                <div className={styles.row}>
                  <strong>{a.label}</strong>
                  <span>
                    {a.kind} · {a.currency} · {a.status}
                  </span>
                </div>
                <p className={styles.muted}>
                  {a.statements_through ? `Statements through ${formatDate(a.statements_through)}` : "No statement uploaded"}
                  {a.attested_through ? ` · confirmed through ${formatDate(a.attested_through)}` : ""} · {a.coverage_status}
                </p>
                <div className={styles.actions}>
                  <Button onClick={() => setUploading(a.id)}>Upload statement</Button>
                  <Button onClick={() => setAttesting(a.id)}>Confirm no other payments</Button>
                  <Link to={`../reconciliation/confirmed`} relative="path">
                    View Transactions
                  </Link>
                </div>
              </li>
            ))}
          </ul>
        )}
      </QueryState>
      {declaring && <DeclareDialog workspace={ws} onClose={() => setDeclaring(false)} />}
      {uploading && <StatementDialog workspace={ws} accountId={uploading} onClose={() => setUploading(null)} />}
      {attesting && <AttestDialog workspace={ws} accountId={attesting} onClose={() => setAttesting(null)} />}
    </div>
  );
}
