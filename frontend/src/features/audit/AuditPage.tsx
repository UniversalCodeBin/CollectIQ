import { useInfiniteQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useParams } from "react-router";
import { QueryState } from "../../components/ui/QueryState";
import { apiRequest } from "../../lib/api";
import styles from "../automation/Automation.module.css";

/** Audit History (E099, E100, SCR-12). Read-only: there is no way here to edit or remove a record. */
export function AuditPage() {
  const { ws = "" } = useParams();
  const [action, setAction] = useState("");
  const [applied, setApplied] = useState("");
  const [exportNote, setExportNote] = useState<string | null>(null);

  const events = useInfiniteQuery({
    queryKey: ["audit", ws, applied],
    initialPageParam: undefined as string | undefined,
    queryFn: ({ pageParam }) =>
      apiRequest(
        { method: "get", path: "/api/v1/workspaces/{ws}/audit-events" },
        {
          path: { ws },
          query: {
            limit: "50",
            ...(applied ? { action: applied } : {}),
            ...(pageParam ? { cursor: pageParam } : {}),
          },
        },
      ),
    getNextPageParam: (last) => last.next_cursor ?? undefined,
  });

  async function download(format: "CSV" | "JSON") {
    setExportNote(null);
    try {
      const filters: { [key: string]: string } = applied
        ? { action: applied }
        : {};
      const result = await apiRequest(
        {
          method: "post",
          path: "/api/v1/workspaces/{ws}/audit-events/exports",
        },
        { path: { ws }, body: { format, filters } },
        { idempotencyKey: crypto.randomUUID() },
      );
      const blob = new Blob([result.content], {
        type: format === "CSV" ? "text/csv" : "application/json",
      });
      const link = document.createElement("a");
      link.href = URL.createObjectURL(blob);
      link.download = result.filename;
      link.click();
      URL.revokeObjectURL(link.href);
      setExportNote(
        `Exported ${result.rows} records.${result.truncated ? " The export was cut at its limit." : ""}`,
      );
    } catch {
      setExportNote("The export could not be made. Nothing was downloaded.");
    }
  }

  const pages = events.data?.pages ?? [];
  const notice = pages[0]?.notice;
  return (
    <div className={styles.page}>
      <h1 className={styles.title}>Audit History</h1>
      {notice && <p className={styles.muted}>{notice}</p>}
      <form
        onSubmit={(event) => {
          event.preventDefault();
          setApplied(action.trim());
        }}
        style={{ display: "flex", gap: "var(--space-2)", alignItems: "end" }}
      >
        <label>
          Action
          <input
            value={action}
            onChange={(event) => setAction(event.target.value)}
            placeholder="reminder.approved"
          />
        </label>
        <button type="submit">Search</button>
        <button type="button" onClick={() => void download("CSV")}>
          Export CSV
        </button>
        <button type="button" onClick={() => void download("JSON")}>
          Export JSON
        </button>
      </form>
      {exportNote && <p role="status">{exportNote}</p>}
      <QueryState query={events} label="audit events">
        <table className={styles.card}>
          <caption className="sr-only">Audit events, newest first</caption>
          <thead>
            <tr>
              <th scope="col">When</th>
              <th scope="col">Actor</th>
              <th scope="col">Action</th>
              <th scope="col">Object</th>
              <th scope="col">Reasons</th>
            </tr>
          </thead>
          <tbody>
            {pages.flatMap((page) =>
              page.items.map((item) => (
                <tr key={item.id}>
                  <td>{item.occurred_at}</td>
                  <td>{item.actor_type}</td>
                  <td>{item.action}</td>
                  <td>
                    {item.object_type} {item.object_id}
                  </td>
                  <td>{item.reason_codes.join(", ")}</td>
                </tr>
              )),
            )}
          </tbody>
        </table>
        {pages.length > 0 && pages[0]?.items.length === 0 && (
          <p>No audit records match.</p>
        )}
        {events.hasNextPage && (
          <button
            type="button"
            onClick={() => void events.fetchNextPage()}
            disabled={events.isFetchingNextPage}
          >
            Show older records
          </button>
        )}
      </QueryState>
    </div>
  );
}
