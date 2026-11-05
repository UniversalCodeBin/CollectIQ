import { useQuery } from "@tanstack/react-query";
import { useParams } from "react-router";
import { QueryState } from "../../components/ui/QueryState";
import { apiRequest } from "../../lib/api";
import styles from "../automation/Automation.module.css";

/** AI payload inspector (E105): what was sent to the provider, with personal details already replaced by tokens. */
export function PayloadsPanel() {
  const { ws = "" } = useParams();
  const payloads = useQuery({
    queryKey: ["ai-payloads", ws],
    queryFn: () =>
      apiRequest(
        { method: "get", path: "/api/v1/workspaces/{ws}/ai/payloads" },
        { path: { ws } },
      ),
  });
  return (
    <div className={styles.page}>
      <h1 className={styles.title}>AI payload inspector</h1>
      <p className={styles.muted}>
        {payloads.data?.note ??
          "Shown as sent, with personal details replaced by tokens."}{" "}
        Opening this page is recorded in the audit history.
      </p>
      <QueryState query={payloads} label="AI payloads">
        {(payloads.data?.items ?? []).map((item) => (
          <section key={item.id} className={styles.card}>
            <h2>
              {item.task_id} · {item.status}
            </h2>
            <p className={styles.muted}>
              {item.created_at} · {item.provider ?? "no provider"} · hash{" "}
              {item.input_sha256 ?? "none"}
            </p>
            {item.dropped_fields.length > 0 && (
              <p>Fields not sent: {item.dropped_fields.join(", ")}</p>
            )}
            <pre>
              {item.payload
                ? JSON.stringify(item.payload, null, 2)
                : "Cleared by the retention window."}
            </pre>
          </section>
        ))}
        {payloads.data?.items.length === 0 && (
          <p>Nothing has been sent to an AI provider.</p>
        )}
      </QueryState>
    </div>
  );
}
