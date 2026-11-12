// FILE GUIDE: audit history (SCR-12). Read-only: nothing on this screen can edit or remove a record. The only claim
// made about the trail is the notice the server sends with every page, shown as it arrives.
import { useInfiniteQuery } from "@tanstack/react-query";
import { type FormEvent, Fragment, type ReactNode, useState } from "react";
import { Link, useParams } from "react-router";
import { AiMark } from "../../components/domain/AiMark";
import { Button } from "../../components/ui/Button";
import { Callout } from "../../components/ui/Callout";
import { type Column, DataTable } from "../../components/ui/DataTable";
import { TextField } from "../../components/ui/Field";
import { Page, PageHeader, Section } from "../../components/ui/Page";
import { QueryState } from "../../components/ui/QueryState";
import { apiRequest } from "../../lib/api";
import type { components } from "../../lib/api-types";
import { formatDate } from "../../lib/format";
import styles from "./Audit.module.css";

type AuditEvent = components["schemas"]["AuditEventOut"];

/** Where the record's object can be read in full. The invoice page explains why it is in its state. */
function objectPath(ws: string, type: string, id: string): string | null {
  if (type === "invoice") return `/w/${ws}/invoices/${id}/overview`;
  if (type === "reminder") return `/w/${ws}/reminders/${id}`;
  return null;
}

const ACTORS: Record<string, string> = { USER: "A person", SYSTEM: "CollectIQ", AI: "AI" };

/** Date and time in UTC, so two people in different time zones read the same moment the same way. */
function when(iso: string): string {
  const at = new Date(iso);
  if (Number.isNaN(at.getTime())) return iso;
  const utc = at.toISOString();
  return `${formatDate(utc)}, ${utc.slice(11, 16)} UTC`;
}

const hasChange = (value: unknown) => value !== null && value !== undefined;

/** Offers a line break after each dot, so a long action such as conversation.interpreted wraps at the dot. */
function breakable(text: string): ReactNode {
  return text.split(/(?<=\.)/).map((part, index) => (
    <Fragment key={index}>
      {index > 0 && <wbr />}
      {part}
    </Fragment>
  ));
}

export function AuditPage() {
  const { ws = "" } = useParams();
  const [action, setAction] = useState("");
  const [applied, setApplied] = useState("");
  const [exporting, setExporting] = useState<"CSV" | "JSON" | null>(null);
  const [exportNote, setExportNote] = useState<{ ok: boolean; text: string } | null>(null);

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

  function search(event: FormEvent) {
    event.preventDefault();
    setApplied(action.trim());
  }

  function clear() {
    setAction("");
    setApplied("");
  }

  async function download(format: "CSV" | "JSON") {
    if (exporting) return;
    setExportNote(null);
    setExporting(format);
    try {
      const filters: { [key: string]: string } = applied ? { action: applied } : {};
      const result = await apiRequest(
        { method: "post", path: "/api/v1/workspaces/{ws}/audit-events/exports" },
        { path: { ws }, body: { format, filters } },
        { idempotencyKey: crypto.randomUUID() },
      );
      const blob = new Blob([result.content], { type: format === "CSV" ? "text/csv" : "application/json" });
      const link = document.createElement("a");
      link.href = URL.createObjectURL(blob);
      link.download = result.filename;
      link.click();
      URL.revokeObjectURL(link.href);
      setExportNote({
        ok: true,
        text: `Exported ${result.rows} records as ${result.filename}.${result.truncated ? " The export stopped at its size limit; narrow the search to get the rest." : ""}`,
      });
    } catch {
      setExportNote({ ok: false, text: "The export could not be made. Nothing was downloaded." });
    } finally {
      setExporting(null);
    }
  }

  const pages = events.data?.pages ?? [];
  const notice = pages[0]?.notice;
  const rows = pages.flatMap((page) => page.items);
  const loadingMore = events.isFetchingNextPage;

  const columns: Array<Column<AuditEvent>> = [
    {
      key: "occurred_at",
      header: "When",
      rowHeader: true,
      render: (row) => (
        <time className={styles.mono} dateTime={row.occurred_at}>
          {when(row.occurred_at)}
        </time>
      ),
    },
    {
      key: "actor_type",
      header: "Who",
      render: (row) => (row.actor_type === "AI" ? <AiMark label="AI" /> : (ACTORS[row.actor_type] ?? row.actor_type)),
    },
    {
      key: "action",
      header: "Action",
      render: (row) => <span className={styles.code}>{breakable(row.action)}</span>,
    },
    {
      key: "object",
      header: "Record",
      wide: true,
      render: (row) => {
        const to = objectPath(ws, row.object_type, row.object_id);
        return (
          <div className={styles.record}>
            <span>
              {row.object_type} <span className={styles.id}>{row.object_id}</span>
            </span>
            {to && (
              <Link to={to} className={styles.link}>
                {row.object_type === "invoice" ? "See why" : "Open"}
              </Link>
            )}
            {(hasChange(row.before) || hasChange(row.after)) && (
              <details className={styles.details}>
                <summary>Show what changed</summary>
                <pre className={styles.pre} tabIndex={0} aria-label="Before and after, with personal details masked">
                  {JSON.stringify({ before: row.before, after: row.after }, null, 2)}
                </pre>
              </details>
            )}
          </div>
        );
      },
    },
    {
      key: "reason_codes",
      header: "Reasons",
      render: (row) =>
        row.reason_codes.length > 0 ? (
          <span className={styles.code}>{breakable(row.reason_codes.join(", "))}</span>
        ) : (
          <span className={styles.muted}>None</span>
        ),
    },
  ];

  return (
    <Page>
      <PageHeader
        title="Audit history"
        description="Approvals, sends, imports, policy changes and other consequential actions in this workspace, newest first. You can read and export these records; nothing here can change them."
        actions={
          <>
            <Button
              busy={exporting === "CSV"}
              aria-disabled={exporting !== null || undefined}
              onClick={() => void download("CSV")}
            >
              Export CSV
            </Button>
            <Button
              busy={exporting === "JSON"}
              aria-disabled={exporting !== null || undefined}
              onClick={() => void download("JSON")}
            >
              Export JSON
            </Button>
          </>
        }
      />

      {exportNote && (
        <p role={exportNote.ok ? "status" : "alert"} className={exportNote.ok ? styles.done : styles.error}>
          {exportNote.text}
        </p>
      )}

      {notice && (
        <Callout tone="info" title="What this record can and cannot show">
          {notice}
        </Callout>
      )}

      <Section
        title="Records"
        description={
          applied
            ? `Showing records with the action ${applied}. Exports use the same search.`
            : "Exports include every record, or only those matching your search."
        }
      >
        <form className={styles.filter} onSubmit={search} role="search" aria-label="Audit records">
          <TextField
            label="Action"
            hint="The exact action name, such as reminder.approved."
            value={action}
            spellCheck={false}
            autoCapitalize="off"
            onChange={(event) => setAction(event.target.value)}
          />
          <div className={styles.filterActions}>
            <Button variant="primary" type="submit">
              Search
            </Button>
            {applied && (
              <Button variant="quiet" type="button" onClick={clear}>
                Show all records
              </Button>
            )}
          </div>
        </form>

        <QueryState query={events} label="audit records">
          <DataTable
            caption="Audit records, newest first"
            columns={columns}
            rows={rows}
            rowKey={(row) => String(row.id)}
            empty={
              <p className={styles.muted}>
                {applied
                  ? `No records have the action ${applied}.`
                  : "Nothing has been recorded in this workspace yet."}
              </p>
            }
          />
          {events.hasNextPage && (
            <div className={styles.more}>
              <Button
                busy={loadingMore}
                aria-disabled={loadingMore || undefined}
                onClick={() => !loadingMore && void events.fetchNextPage()}
              >
                Show older records
              </Button>
            </div>
          )}
        </QueryState>
      </Section>
    </Page>
  );
}
