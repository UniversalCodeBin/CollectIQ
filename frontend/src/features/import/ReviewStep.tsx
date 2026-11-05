import { useEffect, useId, useRef, useState } from "react";
import { Button } from "../../components/ui/Button";
import { Dialog } from "../../components/ui/Dialog";
import { MutationFeedback } from "../../components/ui/MutationFeedback";
import { ProblemMessage } from "../../components/ui/ProblemMessage";
import { ApiProblem, apiText, useApiMutation } from "../../lib/api";
import { formatMinor } from "../../lib/format";
import { type Choice, ChoiceGroup } from "./ChoiceGroup";
import { commitBlockers, invalidCount, isDecided, rowsOf, toCommitBody, undecidedClients } from "./decisions";
import styles from "./ImportPage.module.css";
import { type ClientMatch, type Decisions, type ImportBatch, NO_DECISIONS, type ReviewRow, type RowDecision } from "./types";

const ROW_CHOICES: Record<string, Choice> = {
  UPDATE: { value: "UPDATE", label: "Update the existing invoice" },
  KEEP_BOTH: { value: "KEEP_BOTH", label: "Keep both" },
  MERGE: { value: "MERGE", label: "Merge into the existing invoice" },
  IGNORE: { value: "IGNORE", label: "Ignore this row" },
};
const STATUS_TEXT: Record<string, string> = {
  UPDATED: "Matches an invoice you already have",
  POSSIBLE_DUPLICATE: "Might be a copy of an invoice you already have",
  INVALID: "Has problems",
  CONFLICT: "The total and the lines disagree",
};

const plural = (count: number, one: string, many: string) => `${count} ${count === 1 ? one : many}`;

function RowDecisionControl({ row, decisions, onChoose }: { row: ReviewRow; decisions: Decisions; onChoose: (decision: RowDecision) => void }) {
  const name = `${row.row}, ${row.invoice_number ?? "no invoice number"}`;
  const current = decisions.rows[row.row];
  if (row.status === "CONFLICT" && row.conflict) {
    const currency = row.currency ?? "INR";
    const choices: Choice[] = [
      { value: "TOTAL", label: `Total on the invoice: ${formatMinor(row.conflict.total_minor, currency)}` },
      { value: "SUM", label: `Sum of the lines: ${formatMinor(row.conflict.sum_minor, currency)}` },
      ROW_CHOICES["IGNORE"] as Choice,
    ];
    return (
      <ChoiceGroup
        label={`Which total to keep for row ${name}`}
        choices={choices}
        value={current?.total_source ?? current?.action}
        onChange={(value) => onChoose(value === "IGNORE" ? { action: "IGNORE" } : { total_source: value as "TOTAL" | "SUM" })}
      />
    );
  }
  const choices = row.allowed_decisions.map((decision) => ROW_CHOICES[decision]).filter((choice): choice is Choice => Boolean(choice));
  if (choices.length === 0) return null;
  return (
    <ChoiceGroup
      label={`What to do with row ${name}`}
      choices={choices}
      value={current?.action}
      onChange={(value) => onChoose({ action: value as RowDecision["action"] })}
    />
  );
}

function RowCard({ row, decisions, onChoose }: { row: ReviewRow; decisions: Decisions; onChoose: (decision: RowDecision) => void }) {
  return (
    <li className={styles.row} data-decided={isDecided(row, decisions) || undefined}>
      <p className={styles.rowTitle}>
        <strong>Row {row.row}</strong> · {row.invoice_number ?? "No invoice number"} · {row.client_name ?? "No client"}
      </p>
      <p className={styles.hint}>{STATUS_TEXT[row.status] ?? row.status}</p>
      {row.errors.length > 0 && (
        <ul className={styles.errors}>
          {row.errors.map((error, index) => (
            <li key={`${error.field}-${index}`}>{error.message}</li>
          ))}
        </ul>
      )}
      {row.diffs.length > 0 && (
        <ul className={styles.diffs}>
          {row.diffs.map((diff) => (
            <li key={diff.field}>
              {diff.field.replace(/_/g, " ")}: {String(diff.current ?? "empty")} → {String(diff.incoming ?? "empty")}
              {diff.kept && " (your own edit is kept)"}
            </li>
          ))}
        </ul>
      )}
      {row.matches.length > 0 && (
        <ul className={styles.diffs}>
          {row.matches.map((match) => (
            <li key={match.invoice_id}>
              Existing invoice {match.invoice_number}, {formatMinor(match.gross_minor, match.currency)}
              {match.issue_date ? `, issued ${match.issue_date}` : ""}
            </li>
          ))}
        </ul>
      )}
      <RowDecisionControl row={row} decisions={decisions} onChoose={onChoose} />
    </li>
  );
}

function ClientCard({ match, decisions, onChoose }: { match: ClientMatch; decisions: Decisions; onChoose: (choice: string) => void }) {
  const choices: Choice[] = [
    ...match.candidates.map((candidate) => ({ value: `LINK:${candidate.client_id}`, label: `Same client as ${candidate.display_name}` })),
    ...match.in_file.map((other) => ({ value: `SAME_AS:${other}`, label: `Same client as “${other}” in this file` })),
    { value: "NEW", label: "A new client" },
  ];
  const current = decisions.clients[match.name];
  const value = !current ? undefined : current.action === "LINK" ? `LINK:${current.client_id}` : current.action === "SAME_AS" ? `SAME_AS:${current.name}` : "NEW";
  return (
    <li className={styles.row}>
      <p className={styles.rowTitle}>
        <strong>{match.display_name}</strong> · {plural(match.rows, "row", "rows")}
      </p>
      <ChoiceGroup label={`Who is “${match.display_name}”?`} choices={choices} value={value} onChange={onChoose} />
    </li>
  );
}

function download(text: string) {
  const link = document.createElement("a");
  const url = URL.createObjectURL(new Blob([text], { type: "text/csv" }));
  link.href = url;
  link.download = "import-errors.csv";
  link.click();
  URL.revokeObjectURL(url);
}

type Props = { workspace: string; batch: ImportBatch; onChanged: (batch: ImportBatch) => void; onDiscarded: () => void; onChangeColumns: () => void };

export function ReviewStep({ workspace, batch, onChanged, onDiscarded, onChangeColumns }: Props) {
  const [decisions, setDecisions] = useState<Decisions>(NO_DECISIONS);
  const [confirming, setConfirming] = useState(false);
  const [reportProblem, setReportProblem] = useState<ApiProblem | null>(null);
  const commit = useApiMutation({ method: "post", path: "/api/v1/workspaces/{ws}/imports/{import_id}/commit" }, { idempotent: true });
  const discard = useApiMutation({ method: "delete", path: "/api/v1/workspaces/{ws}/imports/{import_id}" });
  const blockersId = useId();
  const path = { ws: workspace, import_id: batch.id };
  const rows = rowsOf(batch);
  const invalid = invalidCount(batch);
  const blockers = commitBlockers(batch, decisions);
  const handed = useRef<unknown>(null);

  useEffect(() => {
    if (commit.status === "success" && commit.data && handed.current !== commit.data) {
      handed.current = commit.data;
      onChanged(commit.data);
    }
  }, [commit.status, commit.data, onChanged]);
  useEffect(() => {
    if (discard.status === "success") onDiscarded();
  }, [discard.status, onDiscarded]);

  const setRow = (row: number, decision: RowDecision) => setDecisions((now) => ({ ...now, rows: { ...now.rows, [row]: decision } }));
  const setClient = (match: ClientMatch, choice: string) =>
    setDecisions((now) => {
      const [action, rest] = choice.split(/:(.*)/s) as [string, string | undefined];
      const decision =
        action === "LINK" ? { action: "LINK" as const, client_id: rest } : action === "SAME_AS" ? { action: "SAME_AS" as const, name: rest } : { action: "NEW" as const };
      return { ...now, clients: { ...now.clients, [match.name]: decision } };
    });

  async function downloadReport() {
    setReportProblem(null);
    try {
      download(await apiText({ method: "get", path: "/api/v1/workspaces/{ws}/imports/{import_id}/error-report" }, { path }));
    } catch (error) {
      setReportProblem(error instanceof ApiProblem ? error : new ApiProblem({ status: 0, code: "NETWORK", detail: "", correlationId: null }));
    }
  }

  const serverFailed = commit.status === "unknown" && commit.problem !== null && commit.problem.status >= 500;
  const counts = batch.counts;
  const waiting = undecidedClients(batch, decisions).length;

  return (
    <div className={styles.stack}>
      <section className={styles.card} aria-labelledby="review-title">
        <h2 id="review-title" className={styles.heading}>
          Review before importing
        </h2>
        <p className={styles.lead}>
          <span>{batch.file_name}</span>: {plural(counts.total_rows ?? 0, "row", "rows")}. Nothing has been added yet.
        </p>
        <ul className={styles.counts}>
          <li>{counts.new ?? 0} new</li>
          <li>{counts.updated ?? 0} matching an existing invoice</li>
          <li>{counts.duplicate ?? 0} already in your ledger</li>
          <li>{counts.possible_duplicate ?? 0} possible copies</li>
          <li>{counts.conflict ?? 0} with a total to settle</li>
          <li>{invalid} with problems</li>
        </ul>
        {batch.failure_reason && (
          <p role="alert" className={styles.failure}>
            {batch.failure_reason}
          </p>
        )}
      </section>

      {batch.client_matches.some((match) => match.decision_required) && (
        <section className={styles.card} aria-labelledby="clients-title">
          <h3 id="clients-title" className={styles.subheading}>
            Clients to confirm{waiting ? ` (${waiting} to go)` : ""}
          </h3>
          <ul className={styles.list}>
            {batch.client_matches
              .filter((match) => match.decision_required)
              .map((match) => (
                <ClientCard key={match.name} match={match} decisions={decisions} onChoose={(choice) => setClient(match, choice)} />
              ))}
          </ul>
        </section>
      )}

      {rows.length > 0 && (
        <section className={styles.card} aria-labelledby="rows-title">
          <h3 id="rows-title" className={styles.subheading}>
            Rows that need you
          </h3>
          <ul className={styles.list}>
            {rows.map((row) => (
              <RowCard key={row.row} row={row} decisions={decisions} onChoose={(decision) => setRow(row.row, decision)} />
            ))}
          </ul>
        </section>
      )}

      {invalid > 0 && (
        <section className={styles.card}>
          {invalid !== (counts.total_rows ?? 0) && (
            <label className={styles.choice}>
              <input
                type="checkbox"
                checked={decisions.skipInvalid}
                onChange={(event) => setDecisions((now) => ({ ...now, skipInvalid: event.target.checked }))}
              />
              <span>Skip the {plural(invalid, "invalid row", "invalid rows")}</span>
            </label>
          )}
          <div>
            <Button variant="secondary" onClick={() => void downloadReport()}>
              Download error report
            </Button>
          </div>
          {reportProblem && <ProblemMessage problem={reportProblem} />}
        </section>
      )}

      <div className={styles.actions}>
        <div className={styles.commit}>
          {blockers.length === 0 ? (
            <Button variant="primary" onClick={() => commit.submit({ path, body: toCommitBody(decisions) })}>
              Commit Invoices
            </Button>
          ) : (
            <>
              <Button variant="primary" aria-disabled="true" aria-describedby={blockersId}>
                Commit Invoices
              </Button>
              <ul id={blockersId} className={styles.blockers}>
                {blockers.map((reason) => (
                  <li key={reason}>{reason}</li>
                ))}
              </ul>
            </>
          )}
        </div>
        <Button variant="quiet" onClick={onChangeColumns}>
          Change columns
        </Button>
        <Button variant="quiet" onClick={() => setConfirming(true)}>
          Discard import
        </Button>
      </div>

      {serverFailed ? (
        <div role="alert" className={styles.failure}>
          <p>Nothing was created. Something went wrong while saving this import. Your choices are kept, so you can try again.</p>
          <Button variant="secondary" onClick={commit.checkStatus}>
            Try again
          </Button>
        </div>
      ) : (
        <MutationFeedback mutation={commit} />
      )}

      <Dialog open={confirming} onClose={() => setConfirming(false)} title="Discard this import?">
        <p>The uploaded file and your choices are removed. Nothing has been added to your invoices.</p>
        <MutationFeedback mutation={discard} />
        <div className={styles.actions}>
          <Button variant="secondary" onClick={() => setConfirming(false)}>
            Keep import
          </Button>
          <Button variant="danger" onClick={() => discard.submit({ path })}>
            Discard import
          </Button>
        </div>
      </Dialog>
    </div>
  );
}
