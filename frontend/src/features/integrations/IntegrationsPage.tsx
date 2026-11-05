import { useQuery } from "@tanstack/react-query";
import { useParams } from "react-router";
import { QueryState } from "../../components/ui/QueryState";
import { apiRequest } from "../../lib/api";
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
              </li>
            ))}
          </ul>
        )}
      </QueryState>
    </div>
  );
}
