import { useInfiniteQuery, useQuery } from "@tanstack/react-query";
import { useParams } from "react-router";
import { Button } from "../../components/ui/Button";
import { EmptyState } from "../../components/ui/EmptyState";
import { QueryState } from "../../components/ui/QueryState";
import { apiRequest } from "../../lib/api";
import { InvoiceTable } from "../receivables/InvoiceTable";
import styles from "./ClientPage.module.css";

const TONES: Record<string, string> = { NEUTRAL: "Neutral", FRIENDLY: "Friendly", FIRM: "Firm" };
const SENSITIVITY: Record<string, string> = { STANDARD: "Standard", HIGH: "Handle with care", SENSITIVE: "Handle with care" };

export function ClientPage() {
  const { ws = "", id = "" } = useParams();
  const profile = useQuery({
    queryKey: ["client", ws, id],
    queryFn: () => apiRequest({ method: "get", path: "/api/v1/workspaces/{ws}/clients/{client_id}" }, { path: { ws, client_id: id } }),
  });
  const invoices = useInfiniteQuery({
    queryKey: ["client-invoices", ws, id],
    initialPageParam: undefined as string | undefined,
    queryFn: ({ pageParam }) =>
      apiRequest({ method: "get", path: "/api/v1/workspaces/{ws}/invoices" }, { path: { ws }, query: { client_id: id, limit: "50", ...(pageParam ? { cursor: pageParam } : {}) } }),
    getNextPageParam: (last) => last.next_cursor ?? undefined,
  });
  const client = profile.data;
  const rows = invoices.data?.pages.flatMap((page) => page.items) ?? [];

  return (
    <div className={styles.page}>
      <QueryState query={profile} label="the client">
        {client && (
          <>
            <header className={styles.header}>
              <h1 className={styles.title}>{client.display_name}</h1>
              <p className={styles.sub}>
                Tone {TONES[client.tone] ?? client.tone.toLowerCase()} · {SENSITIVITY[client.sensitivity] ?? client.sensitivity.toLowerCase()}
              </p>
            </header>

            <section aria-labelledby="contacts-title" className={styles.card}>
              <h2 id="contacts-title" className={styles.heading}>
                Contacts
              </h2>
              {client.contacts.length === 0 ? (
                <p>No contacts yet</p>
              ) : (
                <ul className={styles.list}>
                  {client.contacts.map((contact) => (
                    <li key={contact.id}>
                      <span>{contact.email}</span>
                      {contact.name && <span className={styles.quiet}> · {contact.name}</span>}
                      {contact.status === "SUPPRESSED" && (
                        <span className={styles.suppressed}>
                          {" "}
                          · Suppressed{contact.suppression_reason ? `: ${contact.suppression_reason}` : ""}. No messages are prepared for this address.
                        </span>
                      )}
                    </li>
                  ))}
                </ul>
              )}
            </section>

            {client.aliases.length > 0 && (
              <section aria-labelledby="aliases-title" className={styles.card}>
                <h2 id="aliases-title" className={styles.heading}>
                  Also known as
                </h2>
                <ul className={styles.list}>
                  {client.aliases.map((alias) => (
                    <li key={alias.id}>{alias.text}</li>
                  ))}
                </ul>
              </section>
            )}

            <section aria-labelledby="invoices-title" className={styles.card}>
              <h2 id="invoices-title" className={styles.heading}>
                Invoices
              </h2>
              <QueryState query={invoices} label="invoices">
                {rows.length === 0 ? (
                  <EmptyState title="No invoices for this client yet" />
                ) : (
                  <>
                    <InvoiceTable workspace={ws} caption={`Invoices for ${client.display_name}`} rows={rows as never} queue={false} />
                    {invoices.hasNextPage && (
                      <div>
                        <Button variant="secondary" onClick={() => void invoices.fetchNextPage()}>
                          Load more
                        </Button>
                      </div>
                    )}
                  </>
                )}
              </QueryState>
            </section>
          </>
        )}
      </QueryState>
    </div>
  );
}
