import { useState } from "react";
import { useParams } from "react-router";
import { apiRequest } from "../../lib/api";
import styles from "../automation/Automation.module.css";

const CONFIRMATION = "DELETE MY WORKSPACE";

/** Export and deletion (E102-E104). Export holds this workspace only; deletion keeps the audit history. */
export function PrivacyPanel() {
  const { ws = "" } = useParams();
  const [exportNote, setExportNote] = useState<string | null>(null);
  const [text, setText] = useState("");
  const [deleteNote, setDeleteNote] = useState<string | null>(null);

  async function requestExport() {
    setExportNote(null);
    try {
      const made = await apiRequest(
        { method: "post", path: "/api/v1/workspaces/{ws}/exports" },
        { path: { ws }, body: {} },
        { idempotencyKey: crypto.randomUUID() },
      );
      setExportNote(
        `Export ${made.id} requested. It is built in the background; check back shortly.`,
      );
    } catch {
      setExportNote("The export could not be requested.");
    }
  }

  async function remove() {
    setDeleteNote(null);
    try {
      const done = await apiRequest(
        { method: "post", path: "/api/v1/workspaces/{ws}/deletion" },
        { path: { ws }, body: { confirmation_text: text } },
        { idempotencyKey: crypto.randomUUID() },
      );
      setDeleteNote(
        `Deleted. ${done.rows_remaining} rows remain after the scan. ${done.note}`,
      );
    } catch {
      setDeleteNote(
        "The workspace was not deleted. Check the confirmation text.",
      );
    }
  }

  return (
    <div className={styles.page}>
      <h1 className={styles.title}>Export and deletion</h1>
      <section className={styles.card}>
        <h2>Export this workspace</h2>
        <p className={styles.muted}>
          The export holds only this workspace. Credentials, sealed values and
          encryption keys are never included.
        </p>
        <button type="button" onClick={() => void requestExport()}>
          Request export
        </button>
        {exportNote && <p role="status">{exportNote}</p>}
      </section>
      <section className={styles.card}>
        <h2>Delete this workspace</h2>
        <p className={styles.muted}>
          Deletes the workspace data and checks that none remains. The audit
          history is kept: it is append-only by database permissions. Only an
          Owner can do this, and it cannot be undone.
        </p>
        <label>
          Type {CONFIRMATION} to confirm
          <input
            value={text}
            onChange={(event) => setText(event.target.value)}
          />
        </label>
        <button
          type="button"
          disabled={text !== CONFIRMATION}
          onClick={() => void remove()}
        >
          Delete workspace
        </button>
        {deleteNote && <p role="status">{deleteNote}</p>}
      </section>
    </div>
  );
}
