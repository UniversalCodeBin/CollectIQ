import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useParams } from "react-router";
import { QueryState } from "../../components/ui/QueryState";
import { apiRequest } from "../../lib/api";
import styles from "../automation/Automation.module.css";

const LABELS: Record<string, string> = {
  CASE_OPENED: "A case is opened",
  REMINDER_DRAFT_READY: "A reminder draft is ready to review",
};

/** In-app notification choices (E125, E126). Personal. Switching one off never hides work from the review inbox. */
export function NotificationsPanel() {
  const { ws = "" } = useParams();
  const client = useQueryClient();
  const key = ["notification-preferences", ws];
  const prefs = useQuery({
    queryKey: key,
    queryFn: () =>
      apiRequest(
        { method: "get", path: "/api/v1/workspaces/{ws}/notification-preferences" },
        { path: { ws } },
      ),
  });
  async function change(kind: string, on: boolean) {
    await apiRequest(
      { method: "put", path: "/api/v1/workspaces/{ws}/notification-preferences" },
      { path: { ws }, body: { in_app: { [kind]: on } } },
      { idempotencyKey: crypto.randomUUID() },
    );
    await client.invalidateQueries({ queryKey: key });
  }
  return (
    <div className={styles.page}>
      <h1 className={styles.title}>Notifications</h1>
      <p className={styles.muted}>
        These choices are yours alone. Work that needs a person still appears in the review inbox either way.
        Notifications are kept for 90 days.
      </p>
      <QueryState query={prefs} label="your notification choices">
        {Object.entries(prefs.data?.in_app ?? {}).map(([kind, on]) => (
          <label key={kind} style={{ display: "block" }}>
            <input type="checkbox" checked={on} onChange={(event) => void change(kind, event.target.checked)} />{" "}
            Tell me in the app when {(LABELS[kind] ?? kind).replace(/^A /, "a ")}
          </label>
        ))}
      </QueryState>
    </div>
  );
}
