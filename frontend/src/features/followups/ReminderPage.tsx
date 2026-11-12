// FILE GUIDE: one reminder (SCR-09, E083–E090). A draft can be edited, approved or rejected; an approved reminder is
// sent by a person, either through a connected Gmail mailbox (they press the button) or outside CollectIQ and then
// recorded here. CollectIQ never sends on its own. The facts panel shows the invoice values the draft was built from.
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Mail } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useParams } from "react-router";
import { SESSION_KEY, type Session } from "../../app/SessionGate";
import { Button } from "../../components/ui/Button";
import buttonStyles from "../../components/ui/Button.module.css";
import { Callout } from "../../components/ui/Callout";
import { Dialog } from "../../components/ui/Dialog";
import { SelectField, TextAreaField, TextField } from "../../components/ui/Field";
import { MutationFeedback } from "../../components/ui/MutationFeedback";
import { Page, PageHeader, Section, Split } from "../../components/ui/Page";
import { QueryState } from "../../components/ui/QueryState";
import { apiRequest, useApiMutation } from "../../lib/api";
import { formatDate, formatMinor } from "../../lib/format";
import styles from "./Followups.module.css";
import { plainReasons, STATUS_TEXT } from "./reasons";

type Method = "EMAIL" | "WHATSAPP" | "PHONE" | "OTHER";
const METHODS: Record<Method, string> = { EMAIL: "Email", WHATSAPP: "WhatsApp", PHONE: "Phone", OTHER: "Another way" };

function SentDialog({ ws, id, onClose }: { ws: string; id: string; onClose: () => void }) {
  const [method, setMethod] = useState<Method>("EMAIL");
  const client = useQueryClient();
  const sent = useApiMutation(
    { method: "post", path: "/api/v1/workspaces/{ws}/reminders/{reminder_id}/mark-sent" },
    { idempotent: true },
  );

  useEffect(() => {
    if (sent.status === "success") {
      void client.invalidateQueries({ queryKey: ["reminder", ws, id] });
      void client.invalidateQueries({ queryKey: ["reminders", ws] });
      onClose();
    }
  }, [sent.status, client, ws, id, onClose]);

  const pending = sent.status === "pending";
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
          <Button
            variant="primary"
            busy={pending}
            aria-disabled={pending || undefined}
            onClick={() =>
              !pending &&
              sent.submit({ path: { ws, reminder_id: id }, body: { sent_at: new Date().toISOString(), method } })
            }
          >
            Record that I sent it
          </Button>
          <Button variant="secondary" data-cancel onClick={onClose}>
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
  const reject = useApiMutation(
    { method: "post", path: "/api/v1/workspaces/{ws}/reminders/{reminder_id}/reject" },
    { idempotent: true },
  );

  useEffect(() => {
    if (reject.status === "success") {
      void client.invalidateQueries({ queryKey: ["reminder", ws, id] });
      void client.invalidateQueries({ queryKey: ["reminders", ws] });
      onClose();
    }
  }, [reject.status, client, ws, id, onClose]);

  const pending = reject.status === "pending";
  return (
    <Dialog open onClose={onClose} title="Reject draft">
      <div className={styles.form}>
        <p className={styles.muted}>The draft is kept for the record and will not be sent.</p>
        <TextField label="Reason (optional)" value={reason} onChange={(e) => setReason(e.target.value)} />
        <MutationFeedback mutation={reject} />
        <div className={styles.actions}>
          <Button
            variant="danger"
            busy={pending}
            aria-disabled={pending || undefined}
            onClick={() =>
              !pending &&
              reject.submit({ path: { ws, reminder_id: id }, body: reason.trim() ? { reason: reason.trim() } : {} })
            }
          >
            Reject draft
          </Button>
          <Button variant="secondary" data-cancel onClick={onClose}>
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
    queryFn: () =>
      apiRequest(
        { method: "get", path: "/api/v1/workspaces/{ws}/reminders/{reminder_id}" },
        { path: { ws, reminder_id: id } },
      ),
  });
  const [text, setText] = useState<string | null>(null);
  const [dialog, setDialog] = useState<"sent" | "reject" | null>(null);
  const [copied, setCopied] = useState(false);
  const edit = useApiMutation(
    { method: "patch", path: "/api/v1/workspaces/{ws}/reminders/{reminder_id}" },
    { ifMatch: true },
  );
  const approve = useApiMutation(
    { method: "post", path: "/api/v1/workspaces/{ws}/reminders/{reminder_id}/approve" },
    { idempotent: true },
  );
  const send = useApiMutation(
    { method: "post", path: "/api/v1/workspaces/{ws}/reminders/{reminder_id}/send" },
    { idempotent: true },
  );
  const resolve = useApiMutation(
    { method: "post", path: "/api/v1/workspaces/{ws}/reminders/{reminder_id}/confirm-unknown" },
    { idempotent: true },
  );
  const integrations = useQuery({
    queryKey: ["integrations", ws],
    queryFn: () => apiRequest({ method: "get", path: "/api/v1/workspaces/{ws}/integrations" }, { path: { ws } }),
  });
  const gmailReady =
    integrations.data?.items.some((i) => i.key === "GMAIL" && i.state === "CONNECTED_VERIFIED") ?? false;
  const refresh = () => {
    void client.invalidateQueries({ queryKey: ["reminder", ws, id] });
    void client.invalidateQueries({ queryKey: ["reminders", ws] });
  };

  useEffect(() => {
    if (
      edit.status === "success" ||
      approve.status === "success" ||
      send.status === "success" ||
      resolve.status === "success"
    ) {
      setText(null);
      refresh();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [edit.status, approve.status, send.status, resolve.status]);

  const r = found.data;
  const live = r?.status === "DRAFT" || r?.status === "APPROVED";
  const blocks = plainReasons(r?.gates?.reasons ?? []);
  const blocked =
    live && r?.gates != null && r.gates.outcome !== "REQUIRE_APPROVAL" && r.gates.outcome !== "ALLOW_AUTOMATIC";
  const body = text ?? r?.body ?? "";
  const unsaved = text !== null;
  const busy = {
    edit: edit.status === "pending",
    approve: approve.status === "pending",
    send: send.status === "pending",
    resolve: resolve.status === "pending",
  };
  const facts = r?.fact_block;
  const currency = typeof facts?.currency === "string" ? facts.currency : "INR";

  async function copy() {
    if (!r) return;
    await navigator.clipboard.writeText(`${r.subject}\n\n${r.body}`);
    setCopied(true);
  }

  return (
    <Page>
      <QueryState query={found} label="the reminder">
        {r && (
          <>
            <PageHeader
              back={{ to: `/w/${ws}/followups`, label: "Follow-ups" }}
              title={r.subject}
              meta={
                <p className={styles.meta}>
                  <Link to={`/w/${ws}/invoices/${r.invoice_id}/overview`} className={styles.reminderLink}>
                    <span className={styles.number}>{r.invoice_number}</span>
                  </Link>
                  <span>To {r.recipient}</span>
                  {r.intended_date && !r.sent_at && (
                    <span>
                      Planned for{" "}
                      <time className={styles.date} dateTime={r.intended_date}>
                        {formatDate(r.intended_date)}
                      </time>
                    </span>
                  )}
                </p>
              }
            />

            <div className={styles.standing}>
              <p role="status" className={styles.statusLine} data-status={r.status}>
                {STATUS_TEXT[r.status] ?? r.status}
              </p>
              {r.status === "APPROVED" && (
                <p className={styles.muted}>
                  CollectIQ has not sent this. Send it with Gmail, or copy the text, send it yourself and record it.
                </p>
              )}
              {r.status === "MARKED_SENT" && (
                <p className={styles.plain}>
                  Marked sent {r.marked_by && r.marked_by === me ? "by you" : "by a team member"}
                  {r.sent_at ? ` on ${formatDate(r.sent_at)}` : ""}.
                </p>
              )}
              {r.reason && (r.status === "REJECTED" || r.status === "CANCELLED") && (
                <p className={styles.muted}>{r.reason}</p>
              )}
            </div>

            {r.status === "SUBMISSION_UNKNOWN" && (
              <Callout tone="error" title="Check whether it went out">
                <p>
                  CollectIQ will not send this again by itself. Look in your Gmail Sent folder, then tell us what you
                  found.
                </p>
                <MutationFeedback mutation={resolve} />
                <div className={styles.actions}>
                  <Button
                    variant="primary"
                    busy={busy.resolve}
                    aria-disabled={busy.resolve || undefined}
                    onClick={() =>
                      !busy.resolve && resolve.submit({ path: { ws, reminder_id: id }, body: { outcome: "WAS_SENT" } })
                    }
                  >
                    It was sent
                  </Button>
                  <Button
                    variant="secondary"
                    aria-disabled={busy.resolve || undefined}
                    onClick={() =>
                      !busy.resolve && resolve.submit({ path: { ws, reminder_id: id }, body: { outcome: "NOT_SENT" } })
                    }
                  >
                    It was not sent
                  </Button>
                </div>
              </Callout>
            )}

            {blocked && (
              <Callout tone="paused" title="Why this is held">
                <ul className={styles.reasons}>
                  {(blocks.length ? blocks : ["A rule is holding this reminder."]).map((line) => (
                    <li key={line}>{line}</li>
                  ))}
                </ul>
              </Callout>
            )}

            <Split
              rail={
                facts && (
                  <Section
                    level={3}
                    title="From the invoice"
                    description="The values this draft was built from. If the invoice changes, the draft is held until it is refreshed."
                  >
                    <dl className={styles.facts}>
                      <div>
                        <dt>Invoice</dt>
                        <dd className={styles.number}>{r.invoice_number}</dd>
                      </div>
                      {typeof facts.outstanding_minor === "number" && (
                        <div>
                          <dt>Amount outstanding</dt>
                          <dd className={styles.amount}>{formatMinor(facts.outstanding_minor, currency)}</dd>
                        </div>
                      )}
                      {typeof facts.due_date === "string" && (
                        <div>
                          <dt>Due date</dt>
                          <dd className={styles.number}>{formatDate(facts.due_date)}</dd>
                        </div>
                      )}
                    </dl>
                  </Section>
                )
              }
            >
              <Section
                title="Message"
                description={
                  r.status === "DRAFT"
                    ? "Edit the wording if you need to. Keep the invoice number, the amount outstanding and the due date in it."
                    : "The wording as it stands. Only a draft can be edited."
                }
              >
                <div className={styles.form}>
                  <TextAreaField
                    label="Message text"
                    rows={10}
                    value={body}
                    readOnly={r.status !== "DRAFT"}
                    onChange={(e) => setText(e.target.value)}
                  />
                  <MutationFeedback mutation={edit} />
                  <MutationFeedback mutation={approve} />
                  <MutationFeedback mutation={send} />

                  {r.status === "DRAFT" && (
                    <div className={styles.actions}>
                      <Button
                        variant="primary"
                        busy={busy.approve}
                        aria-disabled={blocked || unsaved || busy.approve || undefined}
                        onClick={() =>
                          !blocked && !unsaved && !busy.approve && approve.submit({ path: { ws, reminder_id: id } })
                        }
                      >
                        Approve and mark ready to send
                      </Button>
                      <Button
                        variant="secondary"
                        busy={busy.edit}
                        aria-disabled={busy.edit || undefined}
                        onClick={() =>
                          !busy.edit &&
                          edit.submit({ path: { ws, reminder_id: id }, body: { body }, version: r.version })
                        }
                      >
                        Save changes
                      </Button>
                      <Button variant="danger" className={styles.pushEnd} onClick={() => setDialog("reject")}>
                        Reject draft
                      </Button>
                    </div>
                  )}
                  {unsaved && r.status === "DRAFT" && (
                    <p className={styles.muted}>Save your changes before approving.</p>
                  )}

                  {r.status === "APPROVED" && (
                    <>
                      <div className={styles.actions}>
                        {gmailReady && (
                          <Button
                            variant="primary"
                            busy={busy.send}
                            aria-disabled={busy.send || undefined}
                            onClick={() => !busy.send && send.submit({ path: { ws, reminder_id: id } })}
                          >
                            Send with Gmail
                          </Button>
                        )}
                        <Button variant={gmailReady ? "secondary" : "primary"} onClick={() => setDialog("sent")}>
                          I sent it
                        </Button>
                        <Button variant="secondary" onClick={() => void copy()}>
                          Copy message text
                        </Button>
                        {r.recipient.includes("@") && (
                          <a
                            className={`${buttonStyles.button} ${buttonStyles.link}`}
                            data-variant="secondary"
                            data-size="md"
                            href={`mailto:${r.recipient}?subject=${encodeURIComponent(r.subject)}&body=${encodeURIComponent(r.body)}`}
                          >
                            <Mail size={16} aria-hidden="true" />
                            Open in email client
                          </a>
                        )}
                        <Button variant="danger" className={styles.pushEnd} onClick={() => setDialog("reject")}>
                          Reject draft
                        </Button>
                      </div>
                      {!gmailReady && (
                        <p className={styles.muted}>
                          To send from here, connect Gmail under Integrations.{" "}
                          <Link to={`/w/${ws}/integrations`} className={styles.textLink}>
                            Go to Integrations
                          </Link>
                        </p>
                      )}
                      {copied && (
                        <p role="status" className={styles.muted}>
                          Copied. Nothing has been sent.
                        </p>
                      )}
                    </>
                  )}
                </div>
              </Section>

              <p className={styles.footnote}>
                CollectIQ never sends a reminder by itself. Approving records who approved it. It goes out through Gmail
                only when a person presses Send with Gmail; otherwise a person sends it and records that here.
              </p>
            </Split>

            {dialog === "sent" && <SentDialog ws={ws} id={id} onClose={() => setDialog(null)} />}
            {dialog === "reject" && <RejectDialog ws={ws} id={id} onClose={() => setDialog(null)} />}
          </>
        )}
      </QueryState>
    </Page>
  );
}
