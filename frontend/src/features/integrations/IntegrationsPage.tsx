import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect } from "react";
import { useParams } from "react-router";
import { Button } from "../../components/ui/Button";
import { MutationFeedback } from "../../components/ui/MutationFeedback";
import { QueryState } from "../../components/ui/QueryState";
import { apiRequest, useApiMutation } from "../../lib/api";
import styles from "../automation/Automation.module.css";

const STATE_TEXT: Record<string, string> = {
  FILE_BASED: "File based",
  MANUAL: "Manual",
  NEEDS_CONFIGURATION: "Needs configuration",
  SANDBOX_ONLY: "Sandbox only",
  CONNECTED_VERIFIED: "Connected and verified",
  NEEDS_REAUTH: "Needs re-authorization",
  DEGRADED: "Degraded",
  DISCONNECTED: "Disconnected",
};

/** Connect (E094) sends the person to Google to approve; Disconnect (E097) revokes. Neither sends any message. */
function GmailActions({ ws, connected }: { ws: string; connected: boolean }) {
  const client = useQueryClient();
  const connect = useApiMutation({ method: "post", path: "/api/v1/workspaces/{ws}/integrations/gmail/connect" });
  const disconnect = useApiMutation({ method: "delete", path: "/api/v1/workspaces/{ws}/integrations/{key}" }, { idempotent: true });
  const url = connect.data?.authorization_url;
  useEffect(() => {
    if (url) window.location.assign(url);
  }, [url]);
  useEffect(() => {
    if (disconnect.status === "success") void client.invalidateQueries({ queryKey: ["integrations", ws] });
  }, [disconnect.status, client, ws]);
  return (
    <>
      <MutationFeedback mutation={connect} />
      <MutationFeedback mutation={disconnect} />
      {connected ? (
        <Button variant="secondary" onClick={() => disconnect.submit({ path: { ws, key: "GMAIL" } })}>
          Disconnect Gmail
        </Button>
      ) : (
        <Button aria-disabled={connect.status === "pending" || undefined} onClick={() => connect.submit({ path: { ws } })}>
          Connect Gmail
        </Button>
      )}
    </>
  );
}

/** Integrations (E093, SCR-16). A provider only shows as connected after a verification succeeded. */
export function IntegrationsPage() {
  const { ws = "" } = useParams();
  const list = useQuery({
    queryKey: ["integrations", ws],
    queryFn: () => apiRequest({ method: "get", path: "/api/v1/workspaces/{ws}/integrations" }, { path: { ws } }),
  });
  return (
    <div className={styles.page}>
      <h1 className={styles.title}>Integrations</h1>
      <QueryState query={list} label="integrations">
        {list.data && (
          <ul className={styles.card} style={{ listStyle: "none", padding: 0 }}>
            {list.data.items.map((item) => (
              <li key={item.key} style={{ display: "grid", gap: "var(--space-1)", padding: "var(--space-2) 0" }}>
                <strong>{item.label}</strong>
                <span>{STATE_TEXT[item.state] ?? item.state}</span>
                <span className={styles.muted}>{item.note}</span>
                {item.verified_at && <span className={styles.muted}>Verified {item.verified_at}</span>}
                {item.last_error && <span role="status">{item.last_error}</span>}
                {item.key === "GMAIL" && <GmailActions ws={ws} connected={item.state === "CONNECTED_VERIFIED"} />}
              </li>
            ))}
          </ul>
        )}
      </QueryState>
    </div>
  );
}
