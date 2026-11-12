import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useParams } from "react-router";
import { Button } from "../../components/ui/Button";
import { TextField } from "../../components/ui/Field";
import { MutationFeedback } from "../../components/ui/MutationFeedback";
import { QueryState } from "../../components/ui/QueryState";
import { apiRequest, useApiMutation } from "../../lib/api";
import { formatDate } from "../../lib/format";
import styles from "./Followups.module.css";
import { plainReasons } from "./reasons";

/**
 * What the customer has said about paying (FL-08) and the pause in reminders that can follow (FL-09).
 * A stated date is recorded by a person. A pause starts only after an approval (E092 then E074) and a person
 * can end it at any time (E075). A promise never marks anything paid.
 */
export function CommitmentsPanel({ invoiceId }: { invoiceId: string }) {
  const { ws = "" } = useParams();
  const client = useQueryClient();
  const key = ["commitments", ws, invoiceId];
  const [strength, setStrength] = useState<"EXPLICIT" | "TENTATIVE">("EXPLICIT");
  const [date, setDate] = useState("");
  const [note, setNote] = useState("");
  const [problem, setProblem] = useState<string | null>(null);
  const list = useQuery({
    queryKey: key,
    queryFn: () =>
      apiRequest(
        { method: "get", path: "/api/v1/workspaces/{ws}/invoices/{invoice_id}/commitments" },
        { path: { ws, invoice_id: invoiceId } },
      ),
  });
  const record = useApiMutation({ method: "post", path: "/api/v1/workspaces/{ws}/commitments" }, { idempotent: true });
  const decide = useApiMutation(
    { method: "post", path: "/api/v1/workspaces/{ws}/approvals/{approval_id}/decide" },
    { idempotent: true },
  );
  const start = useApiMutation(
    { method: "post", path: "/api/v1/workspaces/{ws}/invoices/{invoice_id}/snooze/approve" },
    { idempotent: true },
  );
  const undo = useApiMutation(
    { method: "post", path: "/api/v1/workspaces/{ws}/invoices/{invoice_id}/snooze/undo" },
    { idempotent: true },
  );
  const change = useApiMutation(
    { method: "patch", path: "/api/v1/workspaces/{ws}/commitments/{commitment_id}" },
    { ifMatch: true },
  );
  const refresh = () => {
    void client.invalidateQueries({ queryKey: key });
    void client.invalidateQueries({ queryKey: ["invoice", ws, invoiceId] });
  };
  const recordedOk = record.status === "success";
  // The list must show what was just recorded; the proposal alone would hide it.
  useEffect(() => {
    if (recordedOk) void client.invalidateQueries({ queryKey: key });
  }, [recordedOk]); // eslint-disable-line react-hooks/exhaustive-deps
  const recorded = record.status === "success" ? record.data : undefined;
  const proposal = recorded?.snooze ?? null;
  const approvalId = proposal?.approval_id ?? null;
  const proposed = list.data?.snoozes.find((snooze) => snooze.status === "PROPOSED");
  const active = list.data?.snoozes.find((snooze) => snooze.status === "ACTIVE");
  const pendingApproval = approvalId ?? proposed?.approval_id ?? null;

  function save() {
    if (strength === "EXPLICIT" && !date) return setProblem("Pick the date the customer stated.");
    setProblem(null);
    record.submit({
      path: { ws },
      body: {
        invoice_id: invoiceId,
        strength,
        ...(date ? { date } : {}),
        ...(note.trim() ? { note: note.trim() } : {}),
      },
    });
  }

  return (
    <section aria-labelledby="commit-title" className={styles.card}>
      <h2 id="commit-title" className={styles.heading}>
        What the customer said about paying
      </h2>
      <p className={styles.muted}>
        Record a date the customer stated. This is their statement, not a payment: the invoice is only marked paid by
        payment evidence you confirm.
      </p>
      <QueryState query={list} label="the customer's statements">
        <ul>
          {list.data?.items.map((item) => (
            <li key={item.id}>
              {item.strength === "EXPLICIT" ? "Stated date" : "Indicated timing"}:{" "}
              {item.promised_date ? formatDate(item.promised_date) : "no date"} ({item.status.toLowerCase()})
              {item.note ? ` - ${item.note}` : ""}
              {item.status === "ACTIVE" && (
                <>
                  {" "}
                  <Button
                    variant="secondary"
                    onClick={() =>
                      change.submit({
                        path: { ws, commitment_id: item.id },
                        body: { status: "WITHDRAWN" },
                        version: item.version,
                      })
                    }
                  >
                    Withdraw
                  </Button>{" "}
                  <Button
                    variant="secondary"
                    onClick={() =>
                      change.submit({
                        path: { ws, commitment_id: item.id },
                        body: { status: "BROKEN" },
                        version: item.version,
                      })
                    }
                  >
                    Mark as not kept
                  </Button>
                </>
              )}
            </li>
          ))}
          {list.data?.items.length === 0 && <li>Nothing recorded yet.</li>}
        </ul>
        {active && (
          <p role="status">
            Reminders are paused until {formatDate(active.until)}.{" "}
            <Button variant="secondary" onClick={() => undo.submit({ path: { ws, invoice_id: invoiceId }, body: {} })}>
              Undo the pause
            </Button>
          </p>
        )}
      </QueryState>
      <MutationFeedback mutation={change} />
      <MutationFeedback mutation={undo} />
      <label>
        How firm is it?{" "}
        <select value={strength} onChange={(event) => setStrength(event.target.value as "EXPLICIT" | "TENTATIVE")}>
          <option value="EXPLICIT">They gave a date</option>
          <option value="TENTATIVE">They gave rough timing</option>
        </select>
      </label>
      <TextField label="Stated date" type="date" value={date} onChange={(event) => setDate(event.target.value)} />
      <TextField label="Note" value={note} onChange={(event) => setNote(event.target.value)} />
      {problem && <p role="alert">{problem}</p>}
      <div className={styles.actions}>
        <Button onClick={save}>Record what they said</Button>
      </div>
      <MutationFeedback mutation={record} />
      {proposal && !proposal.approval_id && (
        <div role="status">
          <p>Reminders will not be paused automatically.</p>
          <ul>
            {plainReasons(proposal.reasons).map((line) => (
              <li key={line}>{line}</li>
            ))}
          </ul>
        </div>
      )}
      {pendingApproval && !active && (
        <div className={styles.actions}>
          {decide.status !== "success" ? (
            <Button
              onClick={() =>
                decide.submit({ path: { ws, approval_id: pendingApproval }, body: { decision: "APPROVED" } })
              }
            >
              Approve pausing reminders
            </Button>
          ) : (
            <Button
              onClick={() => {
                start.submit({ path: { ws, invoice_id: invoiceId }, body: { approval_id: pendingApproval } });
                refresh();
              }}
            >
              Start the pause
            </Button>
          )}
        </div>
      )}
      <MutationFeedback mutation={decide} />
      <MutationFeedback mutation={start} />
    </section>
  );
}
