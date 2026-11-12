// FILE GUIDE: customer replies (SCR-07). A person pastes what a customer wrote (E063); the list shows every reply
// kept so far (E064). A reply is the customer's statement and nothing more: saving one never changes a balance.
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Sparkles } from "lucide-react";
import { useState } from "react";
import { Link, useParams } from "react-router";
import { Button, ButtonLink } from "../../components/ui/Button";
import { EmptyState } from "../../components/ui/EmptyState";
import { TextAreaField } from "../../components/ui/Field";
import { MutationFeedback } from "../../components/ui/MutationFeedback";
import { Page, PageHeader, Section } from "../../components/ui/Page";
import { QueryState } from "../../components/ui/QueryState";
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

  // Clear the box only once the server has kept the reply.
  if (save.status === "success" && text) {
    setText("");
    void client.invalidateQueries({ queryKey: ["messages", workspace] });
  }

  return (
    <Section
      title="Add a customer reply"
      description="Paste what the customer wrote. It is kept word for word as their statement and never marks anything paid."
    >
      <div className={styles.form}>
        <TextAreaField
          label="Paste the customer's reply"
          rows={5}
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="Paste the email or message the customer sent"
        />
        <MutationFeedback mutation={save} />
        <div className={styles.actions}>
          <Button
            variant="primary"
            busy={save.status === "pending"}
            aria-disabled={save.status === "pending" || undefined}
            onClick={submit}
          >
            Save reply
          </Button>
        </div>
      </div>
    </Section>
  );
}

export function ConversationsPage() {
  const { ws = "" } = useParams();
  const list = useQuery({
    queryKey: ["messages", ws],
    queryFn: () => apiRequest({ method: "get", path: "/api/v1/workspaces/{ws}/messages" }, { path: { ws } }),
  });

  return (
    <Page>
      <PageHeader
        title="Conversations"
        description="What customers have written back about their invoices, kept apart from what is recorded and what is verified."
        actions={
          <ButtonLink to={`/w/${ws}/interpretations`}>
            <Sparkles size={16} aria-hidden="true" />
            Review AI readings
          </ButtonLink>
        }
      />

      <Capture workspace={ws} />

      <Section title="Customer replies" description="Newest first. Open a reply to see what it is linked to.">
        <QueryState query={list} label="conversations">
          {list.data &&
            (list.data.items.length === 0 ? (
              <EmptyState
                title="No customer replies yet"
                body="Paste a reply above to keep it with the invoice it is about."
              />
            ) : (
              <ul aria-label="Customer replies" className={styles.replies}>
                {list.data.items.map((m) => (
                  <li key={m.id} className={styles.reply}>
                    <p className={styles.replyLine}>
                      <Link to={`/w/${ws}/messages/${m.id}`} className={styles.replyLink}>
                        {m.subject ?? "Customer reply"}
                      </Link>
                      <time className={styles.date} dateTime={m.received_at}>
                        {formatDate(m.received_at)}
                      </time>
                    </p>
                    {m.sender && <p className={styles.muted}>From {m.sender}</p>}
                    {m.preview && <p className={styles.preview}>{m.preview}</p>}
                    {m.associations.length > 0 && (
                      <p className={styles.tags}>
                        <span className="visually-hidden">Linked to </span>
                        {m.associations.map((a) => (
                          <span key={a.invoice_id} className={styles.tag}>
                            {a.invoice_number}
                          </span>
                        ))}
                      </p>
                    )}
                  </li>
                ))}
              </ul>
            ))}
        </QueryState>
      </Section>
    </Page>
  );
}
