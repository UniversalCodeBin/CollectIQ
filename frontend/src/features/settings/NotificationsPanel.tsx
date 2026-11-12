import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useParams } from "react-router";
import { Checkbox } from "../../components/ui/Field";
import { Section } from "../../components/ui/Page";
import { QueryState } from "../../components/ui/QueryState";
import { apiRequest } from "../../lib/api";
import styles from "./Settings.module.css";

const LABELS: Record<string, string> = {
  CASE_OPENED: "A case is opened",
  REMINDER_DRAFT_READY: "A reminder draft is ready to review",
};

/** In-app notification choices (E125, E126). Personal. Switching one off never hides work from the review inbox. */
export function NotificationsPanel() {
  const { ws = "" } = useParams();
  const client = useQueryClient();
  const key = ["notification-preferences", ws];
  const [saving, setSaving] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);
  const prefs = useQuery({
    queryKey: key,
    queryFn: () =>
      apiRequest({ method: "get", path: "/api/v1/workspaces/{ws}/notification-preferences" }, { path: { ws } }),
  });

  async function change(kind: string, on: boolean) {
    if (saving) return;
    setSaving(kind);
    setFailed(false);
    try {
      await apiRequest(
        { method: "put", path: "/api/v1/workspaces/{ws}/notification-preferences" },
        { path: { ws }, body: { in_app: { [kind]: on } } },
        { idempotencyKey: crypto.randomUUID() },
      );
      await client.invalidateQueries({ queryKey: key });
    } catch {
      setFailed(true);
    } finally {
      setSaving(null);
    }
  }

  return (
    <Section
      title="Notifications"
      description="These choices are yours alone. Work that needs a person still appears in the review inbox either way. Notifications are kept for 90 days."
    >
      <QueryState query={prefs} label="your notification choices">
        <fieldset className={styles.fieldset} aria-busy={saving ? true : undefined}>
          <legend className={styles.legend}>In the app</legend>
          {Object.entries(prefs.data?.in_app ?? {}).map(([kind, on]) => (
            <Checkbox
              key={kind}
              label={`Tell me in the app when ${(LABELS[kind] ?? kind).replace(/^A /, "a ")}`}
              checked={on}
              disabled={saving !== null}
              onChange={(event) => void change(kind, event.target.checked)}
            />
          ))}
        </fieldset>
        {failed && (
          <p role="alert" className={styles.note}>
            That choice was not saved. Check your connection and try again.
          </p>
        )}
      </QueryState>
    </Section>
  );
}
