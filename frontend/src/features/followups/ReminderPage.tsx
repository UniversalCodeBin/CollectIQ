import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Link, useParams } from "react-router";
import { SESSION_KEY, type Session } from "../../app/SessionGate";
import { Button } from "../../components/ui/Button";
import { Dialog } from "../../components/ui/Dialog";
import { SelectField, TextField } from "../../components/ui/Field";
import { MutationFeedback } from "../../components/ui/MutationFeedback";
import { QueryState } from "../../components/ui/QueryState";
import { apiRequest, useApiMutation } from "../../lib/api";
import { formatDate } from "../../lib/format";
import styles from "./Followups.module.css";
import { plainReasons, STATUS_TEXT } from "./reasons";

type Method = "EMAIL" | "WHATSAPP" | "PHONE" | "OTHER";
const METHODS: Record<Method, string> = { EMAIL: "Email", WHATSAPP: "WhatsApp", PHONE: "Phone", OTHER: "Another way" };

function SentDialog({ ws, id, onClose }: { ws: string; id: string; onClose: () => void }) {
  const [method, setMethod] = useState<Method>("EMAIL");
  const client = useQueryClient();
  const sent = useApiMutation({ method: "post", path: "/api/v1/workspaces/{ws}/reminders/{reminder_id}/mark-sent" }, { idempotent: true });
  useEffect(() => {
    if (sent.status === "success") {
      void client.invalidateQueries({ queryKey: ["reminder", ws, id] });
      void client.invalidateQueries({ queryKey: ["reminders", ws] });
      onClose();
    }
  }, [sent.status, client, ws, id, onClose]);
  return (
    <Dialog open onClose={onClose} title="I sent it">
      <div className={styles.form}>
        <p className={styles.muted}>This records that you sent it yourself. CollectIQ sends nothing.</p>
        <SelectField label="How you sent it" value={method} onChange={(e) => setMethod(e.target.value as Method)}>
          {(Object.keys(METHODS) as Method[]).map((m) => (
            <option key={m} value={m}>
              {METHODS[m]}
            </option>
          ))}
        </SelectField>
        <MutationFeedback mutation={sent} />
        <div className={styles.actions}>
          <Button onClick={() => sent.submit({ path: { ws, reminder_id: id }, body: { sent_at: new Date().toISOString(), method } })}>
            Record that I sent it
          </Button>
          <Button variant="secondary" onClick={onClose}>
            Cancel
          </Button>
        </div>
      </div>
    </Dialog>
  );
}

function RejectDialog({ ws, id, onClose }: { ws: string; id: string; onClose: () => void }) {
  const [reason, setReason] = useState("");
  const client = useQueryClient();
  const reject = useApiMutation({ method: "post", path: "/api/v1/workspaces/{ws}/reminders/{reminder_id}/reject" }, { idempotent: true });
  useEffect(() => {
    if (reject.status === "success") {
      void client.invalidateQueries({ queryKey: ["reminder", ws, id] });
      void client.invalidateQueries({ queryKey: ["reminders", ws] });
      onClose();
    }
  }, [reject.status, client, ws, id, onClose]);
  return (
    <Dialog open onClose={onClose} title="Reject draft">
      <div className={styles.form}>
        <p className={styles.muted}>The draft is kept for the record and will not be sent.</p>
        <TextField label="Reason (optional)" value={reason} onChange={(e) => setReason(e.target.value)} />
        <MutationFeedback mutation={reject} />
        <div className={styles.actions}>
          <Button
            variant="danger"
            onClick={() => reject.submit({ path: { ws, reminder_id: id }, body: reason.trim() ? { reason: reason.trim() } : {} })}
          >
            Reject draft
          </Button>
          <Button variant="secondary" onClick={onClose}>
            Cancel
          </Button>
        </div>
      </div>
    </Dialog>
  );
}

export function ReminderPage() {
  const { ws = "", id = "" } = useParams();
  const client = useQueryClient();
  const me = client.getQueryData<Session>(SESSION_KEY)?.user.id;
  const found = useQuery({
    queryKey: ["reminder", ws, id],
    queryFn: () => apiRequest({ method: "get", path: "/api/v1/workspaces/{ws}/reminders/{reminder_id}" }, { path: { ws, reminder_id: id } }),
  });
  const [text, setText] = useState<string | null>(null);
  const [dialog, setDialog] = useState<"sent" | "reject" | null>(null);
  const [copied, setCopied] = useState(false);
  const edit = useApiMutation({ method: "patch", path: "/api/v1/workspaces/{ws}/reminders/{reminder_id}" }, { ifMatch: true });
  const approve = useApiMutation({ method: "post", path: "/api/v1/workspaces/{ws}/reminders/{reminder_id}/approve" }, { idempotent: true });
  const send = useApiMutation({ method: "post", path: "/api/v1/workspaces/{ws}/reminders/{reminder_id}/send" }, { idempotent: true });
  const resolve = useApiMutation({ method: "post", path: "/api/v1/workspaces/{ws}/reminders/{reminder_id}/confirm-unknown" }, { idempotent: true });
  const integrations = useQuery({
    queryKey: ["integrations", ws],
    queryFn: () => apiRequest({ method: "get", path: "/api/v1/workspaces/{ws}/integrations" }, { path: { ws } }),
  });
  const gmailReady = integrations.data?.items.some((i) => i.key === "GMAIL" && i.state === "CONNECTED_VERIFIED") ?? false;
  const refresh = () => {
    void client.invalidateQueries({ queryKey: ["reminder", ws, id] });
    void client.invalidateQueries({ queryKey: ["reminders", ws] });
  };
  useEffect(() => {
    if (edit.status === "success" || approve.status === "success" || send.status === "success" || resolve.status === "success") {
      setText(null);
      refresh();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [edit.status, approve.status, send.status, resolve.status]);

  const r = found.data;
  const live = r?.status === "DRAFT" || r?.status === "APPROVED";
  const blocks = plainReasons(r?.gates?.reasons ?? []);
  const blocked = live && r?.gates != null && r.gates.outcome !== "REQUIRE_APPROVAL" && r.gates.outcome !== "ALLOW_AUTOMATIC";
  const body = text ?? r?.body ?? "";

  async function copy() {
    if (!r) return;
    await navigator.clipboard.writeText(`${r.subject}\n\n${r.body}`);
    setCopied(true);
  }

  return (
    <div className={styles.page}>
      <QueryState query={found} label="the reminder">
        {r && (
          <>
            <h1 className={styles.title}>{r.subject}</h1>
            <p className={styles.muted}>
              <Link to={`/w/${ws}/invoices/${r.invoice_id}/overview`}>{r.invoice_number}</Link> · to {r.recipient}
            </p>
            <p role="status" className={styles.statusLine}>
              {STATUS_TEXT[r.status] ?? r.status}
            </p>
            {r.status === "APPROVED" && <p className={styles.muted}>CollectIQ has not sent this. Send it with Gmail, or copy the text, send it yourself and record it.</p>}
            {r.status === "SUBMISSION_UNKNOWN" && (
              <section aria-labelledby="unknown-title" className={styles.card}>
                <h2 id="unknown-title" className={styles.heading}>
                  Check whether it went out
                </h2>
                <p>
                  CollectIQ will not send this again by itself. Look in your Gmail Sent folder, then tell us what you found.
                </p>
                <MutationFeedback mutation={resolve} />
                <div className={styles.actions}>
                  <Button onClick={() => resolve.submit({ path: { ws, reminder_id: id }, body: { outcome: "WAS_SENT" } })}>It was sent</Button>
                  <Button variant="secondary" onClick={() => resolve.submit({ path: { ws, reminder_id: id }, body: { outcome: "NOT_SENT" } })}>
                    It was not sent
                  </Button>
                </div>
              </section>
            )}
            {r.status === "MARKED_SENT" && (
              <p>
                Marked sent {r.marked_by && r.marked_by === me ? "by you" : "by a team member"}
                {r.sent_at ? ` on ${formatDate(r.sent_at)}` : ""}.
              </p>
            )}
            {r.reason && (r.status === "REJECTED" || r.status === "CANCELLED") && <p className={styles.muted}>{r.reason}</p>}
            {blocked && (
              <section aria-labelledby="held-title" className={styles.card}>
                <h2 id="held-title" className={styles.heading}>
                  Why this is held
                </h2>
                <ul>{(blocks.length ? blocks : ["A rule is holding this reminder."]).map((line) => <li key={line}>{line}</li>)}</ul>
              </section>
            )}
            <section className={styles.card}>
              <label htmlFor="message-text">Message text</label>
              <textarea
                id="message-text"
                rows={9}
                value={body}
                readOnly={r.status !== "DRAFT"}
                onChange={(e) => setText(e.target.value)}
              />
              <MutationFeedback mutation={edit} />
              <MutationFeedback mutation={approve} />
              <MutationFeedback mutation={send} />
              <div className={styles.actions}>
                {r.status === "DRAFT" && (
                  <>
                    <Button variant="secondary" onClick={() => edit.submit({ path: { ws, reminder_id: id }, body: { body }, version: r.version })}>
                      Save changes
                    </Button>
                    <Button
                      aria-disabled={blocked || text !== null || undefined}
                      onClick={() => !blocked && text === null && approve.submit({ path: { ws, reminder_id: id } })}
                    >
                      Approve and mark ready to send
                    </Button>
                    <Button variant="danger" onClick={() => setDialog("reject")}>
                      Reject draft
                    </Button>
                  </>
                )}
                {r.status === "APPROVED" && (
                  <>
                    <Button variant="secondary" onClick={() => void copy()}>
                      Copy message text
                    </Button>
                    {r.recipient.includes("@") && (
                      <a href={`mailto:${r.recipient}?subject=${encodeURIComponent(r.subject)}&body=${encodeURIComponent(r.body)}`}>
                        Open in email client
                      </a>
                    )}
                    {gmailReady ? (
                      <Button aria-disabled={send.status === "pending" || undefined} onClick={() => send.submit({ path: { ws, reminder_id: id } })}>
                        Send with Gmail
                      </Button>
                    ) : (
                      <span className={styles.muted}>To send from here, connect Gmail under Integrations.</span>
                    )}
                    <Button variant={gmailReady ? "secondary" : "primary"} onClick={() => setDialog("sent")}>
                      I sent it
                    </Button>
                    <Button variant="danger" onClick={() => setDialog("reject")}>
                      Reject draft
                    </Button>
                  </>
                )}
              </div>
              {copied && <p role="status">Copied. Nothing has been sent.</p>}
              {text !== null && r.status === "DRAFT" && <p className={styles.muted}>Save your changes before approving.</p>}
            </section>
            {dialog === "sent" && <SentDialog ws={ws} id={id} onClose={() => setDialog(null)} />}
            {dialog === "reject" && <RejectDialog ws={ws} id={id} onClose={() => setDialog(null)} />}
          </>
        )}
      </QueryState>
    </div>
  );
}
