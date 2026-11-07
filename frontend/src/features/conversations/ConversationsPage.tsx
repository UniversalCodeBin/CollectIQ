import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useParams } from "react-router";
import { Button } from "../../components/ui/Button";
import { EmptyState } from "../../components/ui/EmptyState";
import { QueryState } from "../../components/ui/QueryState";
import { MutationFeedback } from "../../components/ui/MutationFeedback";
import { apiRequest, useApiMutation } from "../../lib/api";
import { formatDate } from "../../lib/format";
import styles from "./Conversations.module.css";

function Capture({ workspace }: { workspace: string }) {
  const [text, setText] = useState("");
  const client = useQueryClient();
  const save = useApiMutation({ method: "post", path: "/api/v1/workspaces/{ws}/messages" }, { idempotent: true });
  function submit() {
    if (!text.trim()) return;
    const body = new FormData();
    body.set("source", "PASTE");
    body.set("text", text);
    save.submit({ path: { ws: workspace }, body });
  }
  if (save.status === "success" && text) {
    setText("");
    void client.invalidateQueries({ queryKey: ["messages", workspace] });
  }
  return (
    <section aria-labelledby="capture-title" className={styles.card}>
      <h2 id="capture-title" className={styles.heading}>
        Add a customer reply
      </h2>
      <p className={styles.muted}>Paste what the customer wrote. It is kept as their statement; it never marks anything paid.</p>
      <div className={styles.form}>
        <label htmlFor="reply-text">Paste the customer's reply</label>
        <textarea id="reply-text" rows={5} value={text} onChange={(e) => setText(e.target.value)} />
        <MutationFeedback mutation={save} />
        <div className={styles.actions}>
          <Button aria-disabled={save.status === "pending" || undefined} onClick={submit}>
            Save reply
          </Button>
        </div>
      </div>
    </section>
  );
}

export function ConversationsPage() {
  const { ws = "" } = useParams();
  const list = useQuery({
    queryKey: ["messages", ws],
    queryFn: () => apiRequest({ method: "get", path: "/api/v1/workspaces/{ws}/messages" }, { path: { ws } }),
  });
  return (
    <div className={styles.page}>
      <h1 className={styles.title}>Conversations</h1>
      <p>
        <Link to={`/w/${ws}/interpretations`}>Replies the AI has read, waiting for your review</Link>
      </p>
      <Capture workspace={ws} />
      <QueryState query={list} label="conversations">
        {list.data &&
          (list.data.items.length === 0 ? (
            <EmptyState title="No customer replies yet" body="Paste a reply above to keep it with the invoice it is about." />
          ) : (
            <ul aria-label="Customer replies" className={styles.list}>
              {list.data.items.map((m) => (
                <li key={m.id} className={styles.card}>
                  <p className={styles.row}>
                    <Link to={`/w/${ws}/messages/${m.id}`}>{m.subject ?? "Customer reply"}</Link>
                    <span className={styles.muted}>{formatDate(m.received_at)}</span>
                  </p>
                  {m.sender && <p className={styles.muted}>From {m.sender}</p>}
                  {m.preview && <p>{m.preview}</p>}
                  <p>
                    {m.associations.map((a) => (
                      <span key={a.invoice_id} className={styles.tag}>
                        {a.invoice_number}
                      </span>
                    ))}
                  </p>
                </li>
              ))}
            </ul>
          ))}
      </QueryState>
    </div>
  );
}
