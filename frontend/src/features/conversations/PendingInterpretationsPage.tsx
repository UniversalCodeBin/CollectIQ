// FILE GUIDE: the queue of AI readings of customer replies that wait for a person (E124).
// Accept (E068), dismiss (E069) and correct (E070) are the only ways a reading takes effect. A reading is
// always labelled as an unverified AI suggestion; none of these actions marks an invoice paid.
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Link, useParams } from "react-router";
import { AiMark } from "../../components/domain/AiMark";
import { Button } from "../../components/ui/Button";
import { EmptyState } from "../../components/ui/EmptyState";
import { SelectField, TextAreaField } from "../../components/ui/Field";
import { MutationFeedback } from "../../components/ui/MutationFeedback";
import { Page, PageHeader } from "../../components/ui/Page";
import { QueryState } from "../../components/ui/QueryState";
import { apiRequest, useApiMutation } from "../../lib/api";
import styles from "./Conversations.module.css";
import { LABEL_TEXT, labelText } from "./labels";

const CONFIDENCE: Record<string, string> = { LOW: "Low", MEDIUM: "Medium", HIGH: "High" };

type Reading = NonNullable<Awaited<ReturnType<typeof fetchPending>>>["items"][number];
const fetchPending = (ws: string) =>
  apiRequest({ method: "get", path: "/api/v1/workspaces/{ws}/interpretations" }, { path: { ws } });

function Decision({ ws, reading, onDone }: { ws: string; reading: Reading; onDone: () => void }) {
  const [correcting, setCorrecting] = useState(false);
  const [intent, setIntent] = useState(reading.primary_label ?? "UNRELATED_OR_AMBIGUOUS");
  const [note, setNote] = useState("");
  const path = { ws, interpretation_id: reading.id };
  const accept = useApiMutation(
    { method: "post", path: "/api/v1/workspaces/{ws}/interpretations/{interpretation_id}/accept" },
    { idempotent: true },
  );
  const dismiss = useApiMutation(
    { method: "post", path: "/api/v1/workspaces/{ws}/interpretations/{interpretation_id}/dismiss" },
    { idempotent: true },
  );
  const correct = useApiMutation(
    { method: "post", path: "/api/v1/workspaces/{ws}/interpretations/{interpretation_id}/correct" },
    { idempotent: true },
  );
  const done = [accept, dismiss, correct].some((m) => m.status === "success");
  useEffect(() => {
    if (done) onDone();
  }, [done, onDone]);
  const busy = [accept, dismiss, correct].some((m) => m.status === "pending");
  return (
    <div className={styles.form}>
      {correcting && (
        <>
          <SelectField label="What the reply says" value={intent} onChange={(e) => setIntent(e.target.value)}>
            {Object.entries(LABEL_TEXT).map(([value, text]) => (
              <option key={value} value={value}>
                {text}
              </option>
            ))}
          </SelectField>
          <TextAreaField
            label="Why you are changing it (required)"
            rows={2}
            value={note}
            onChange={(e) => setNote(e.target.value)}
          />
        </>
      )}
      <MutationFeedback mutation={accept} />
      <MutationFeedback mutation={dismiss} />
      <MutationFeedback mutation={correct} />
      <div className={styles.actions}>
        {correcting ? (
          <>
            <Button
              aria-disabled={busy || !note.trim() || undefined}
              onClick={() => note.trim() && correct.submit({ path, body: { intent, note } })}
            >
              Save correction
            </Button>
            <Button variant="secondary" onClick={() => setCorrecting(false)}>
              Cancel
            </Button>
          </>
        ) : (
          <>
            <Button aria-disabled={busy || undefined} onClick={() => accept.submit({ path, body: {} })}>
              Accept this reading
            </Button>
            <Button variant="secondary" onClick={() => setCorrecting(true)}>
              Correct it
            </Button>
            <Button
              variant="secondary"
              aria-disabled={busy || undefined}
              onClick={() => dismiss.submit({ path, body: {} })}
            >
              Dismiss
            </Button>
          </>
        )}
      </div>
    </div>
  );
}

export function PendingInterpretationsPage() {
  const { ws = "" } = useParams();
  const client = useQueryClient();
  const key = ["interpretations", ws];
  const list = useQuery({ queryKey: key, queryFn: () => fetchPending(ws) });
  const refresh = () => {
    void client.invalidateQueries({ queryKey: key });
    void client.invalidateQueries({ queryKey: ["inbox", ws] });
  };
  return (
    <Page>
      <PageHeader
        back={{ to: `/w/${ws}/conversations`, label: "Conversations" }}
        title="Replies to review"
        description="CollectIQ's AI read these customer replies. Each reading is a suggestion until you accept or correct it, and none of this marks an invoice paid."
      />
      <QueryState query={list} label="replies to review">
        {list.data &&
          (list.data.items.length === 0 ? (
            <EmptyState
              title="Nothing to review"
              body="Readings of customer replies that need a person show up here."
            />
          ) : (
            <ul aria-label="Readings to review" className={styles.readings}>
              {list.data.items.map((r) => (
                <li key={r.id} className={styles.reading}>
                  <p className={styles.readingHead}>
                    <AiMark />
                    <Link to={`/w/${ws}/messages/${r.message_id}`} className={styles.textLink}>
                      Open the reply
                    </Link>
                  </p>
                  {r.status === "NEEDS_MANUAL_REVIEW" ? (
                    <p className={styles.plain}>
                      The AI could not read this reply. Read it yourself and record what it says.
                    </p>
                  ) : (
                    <p className={styles.readingLine}>
                      <span className={styles.readingLabel}>
                        {r.primary_label ? labelText(r.primary_label) : "Unclear"}
                      </span>
                      {r.confidence && (
                        <span className={styles.confidence} data-level={r.confidence}>
                          AI confidence: {CONFIDENCE[r.confidence] ?? r.confidence}
                        </span>
                      )}
                    </p>
                  )}
                  {r.evidence_span && (
                    <blockquote className={styles.quote}>
                      <span className="visually-hidden">The customer wrote: </span>
                      {r.evidence_span}
                    </blockquote>
                  )}
                  {r.date_note && <p className={styles.muted}>{r.date_note}</p>}
                  <Decision ws={ws} reading={r} onDone={refresh} />
                </li>
              ))}
            </ul>
          ))}
      </QueryState>
    </Page>
  );
}
