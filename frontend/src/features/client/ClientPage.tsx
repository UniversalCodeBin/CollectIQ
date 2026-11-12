// FILE GUIDE: client profile (SCR-14). The client's invoices on the left; who to write to, other names it is known
// by and the client-wide reminder pause in the margin. Read-only apart from the pause, which the server enforces.
import { useInfiniteQuery, useQuery } from "@tanstack/react-query";
import { useParams } from "react-router";
import { Button } from "../../components/ui/Button";
import { Page, PageHeader, Section, Split } from "../../components/ui/Page";
import { QueryState } from "../../components/ui/QueryState";
import { apiRequest } from "../../lib/api";
import { PausePanel } from "../followups/PausePanel";
import { InvoiceTable } from "../receivables/InvoiceTable";
import styles from "./ClientPage.module.css";

const TONES: Record<string, string> = { NEUTRAL: "Neutral", FRIENDLY: "Friendly", FIRM: "Firm" };
const SENSITIVITY: Record<string, string> = {
  STANDARD: "Standard",
  HIGH: "Handle with care",
  SENSITIVE: "Handle with care",
};

const plural = (count: number, one: string, many: string) => `${count} ${count === 1 ? one : many}`;

export function ClientPage() {
  const { ws = "", id = "" } = useParams();
  const profile = useQuery({
    queryKey: ["client", ws, id],
    queryFn: () =>
      apiRequest(
        { method: "get", path: "/api/v1/workspaces/{ws}/clients/{client_id}" },
        { path: { ws, client_id: id } },
      ),
  });
  const invoices = useInfiniteQuery({
    queryKey: ["client-invoices", ws, id],
    initialPageParam: undefined as string | undefined,
    queryFn: ({ pageParam }) =>
      apiRequest(
        { method: "get", path: "/api/v1/workspaces/{ws}/invoices" },
        { path: { ws }, query: { client_id: id, limit: "50", ...(pageParam ? { cursor: pageParam } : {}) } },
      ),
    getNextPageParam: (last) => last.next_cursor ?? undefined,
  });
  const client = profile.data;
  const rows = invoices.data?.pages.flatMap((page) => page.items) ?? [];
  const loadingMore = invoices.isFetchingNextPage;
  const back = { to: `/w/${ws}/receivables`, label: "Receivables" };

  if (!client) {
    return (
      <Page>
        <PageHeader title="Client" back={back} />
        <QueryState query={profile} label="the client">
          {null}
        </QueryState>
      </Page>
    );
  }

  const { contacts_active: active, contacts_suppressed: suppressed } = client.summary;
  const contactSummary =
    client.contacts.length === 0
      ? "Who reminders for this client are addressed to."
      : `${plural(active, "address", "addresses")} in use${suppressed ? `, ${suppressed} suppressed` : ""}.`;

  const rail = (
    <>
      <Section title="Contacts" description={contactSummary} level={2}>
        {client.contacts.length === 0 ? (
          <p className={styles.muted}>No contacts yet</p>
        ) : (
          <ul className={styles.contacts}>
            {client.contacts.map((contact) => (
              <li
                key={contact.id}
                className={styles.contact}
                data-suppressed={contact.status === "SUPPRESSED" || undefined}
              >
                <span className={styles.email}>{contact.email}</span>
                {contact.name && <span className={styles.muted}>{contact.name}</span>}
                {contact.status === "SUPPRESSED" && (
                  <span className={styles.suppressed}>
                    Suppressed{contact.suppression_reason ? `: ${contact.suppression_reason}` : ""}. No messages are
                    prepared for this address.
                  </span>
                )}
              </li>
            ))}
          </ul>
        )}
      </Section>

      {client.aliases.length > 0 && (
        <Section
          title="Also known as"
          description="Names that match this client when invoices are imported or payments are matched."
        >
          <ul className={styles.aliases}>
            {client.aliases.map((alias) => (
              <li key={alias.id} className={styles.alias}>
                {alias.text}
              </li>
            ))}
          </ul>
        </Section>
      )}

      <PausePanel scope="CLIENT" targetId={id} />
    </>
  );

  return (
    <Page>
      <PageHeader
        title={client.display_name}
        back={back}
        description="This client's invoices, who reminders go to, and whether reminders are paused."
        meta={
          <dl className={styles.meta}>
            <div>
              <dt>Reminder tone</dt>
              <dd>{TONES[client.tone] ?? client.tone}</dd>
            </div>
            <div>
              <dt>Handling</dt>
              <dd>{SENSITIVITY[client.sensitivity] ?? client.sensitivity}</dd>
            </div>
          </dl>
        }
      />

      <Split rail={rail}>
        <Section
          title="Invoices"
          description="Open the invoice number to see its payments, evidence and follow-up history."
        >
          <QueryState query={invoices} label="invoices">
            {rows.length === 0 ? (
              <p className={styles.muted}>No invoices for this client yet</p>
            ) : (
              <>
                <InvoiceTable
                  workspace={ws}
                  caption={`Invoices for ${client.display_name}`}
                  rows={rows as never}
                  queue={false}
                  showClient={false}
                />
                {invoices.hasNextPage && (
                  <div className={styles.more}>
                    <Button
                      busy={loadingMore}
                      aria-disabled={loadingMore || undefined}
                      onClick={() => !loadingMore && void invoices.fetchNextPage()}
                    >
                      Show more invoices
                    </Button>
                  </div>
                )}
              </>
            )}
          </QueryState>
        </Section>
      </Split>
    </Page>
  );
}
