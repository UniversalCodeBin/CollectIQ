import { useState } from "react";
import { useParams } from "react-router";
import { Button } from "../../components/ui/Button";
import { TextField } from "../../components/ui/Field";
import { Section } from "../../components/ui/Page";
import { apiRequest } from "../../lib/api";
import styles from "./Settings.module.css";

const CONFIRMATION = "DELETE MY WORKSPACE";

/** Export and deletion (E102-E104). Export holds this workspace only; deletion keeps the audit history. */
export function PrivacyPanel() {
  const { ws = "" } = useParams();
  const [exportNote, setExportNote] = useState<string | null>(null);
  const [exporting, setExporting] = useState(false);
  const [text, setText] = useState("");
  const [deleteNote, setDeleteNote] = useState<string | null>(null);
  const [deleting, setDeleting] = useState(false);

  async function requestExport() {
    if (exporting) return;
    setExportNote(null);
    setExporting(true);
    try {
      const made = await apiRequest(
        { method: "post", path: "/api/v1/workspaces/{ws}/exports" },
        { path: { ws }, body: {} },
        { idempotencyKey: crypto.randomUUID() },
      );
      setExportNote(`Export ${made.id} requested. It is built in the background; check back shortly.`);
    } catch {
      setExportNote("The export could not be requested. Try again in a moment.");
    } finally {
      setExporting(false);
    }
  }

  async function remove() {
    if (deleting || text !== CONFIRMATION) return;
    setDeleteNote(null);
    setDeleting(true);
    try {
      const done = await apiRequest(
        { method: "post", path: "/api/v1/workspaces/{ws}/deletion" },
        { path: { ws }, body: { confirmation_text: text } },
        { idempotencyKey: crypto.randomUUID() },
      );
      setDeleteNote(`Deleted. ${done.rows_remaining} rows remain after the scan. ${done.note}`);
    } catch {
      setDeleteNote("The workspace was not deleted. Check the confirmation text. Only an owner can delete it.");
    } finally {
      setDeleting(false);
    }
  }

  return (
    <>
      <Section
        title="Export this workspace"
        description="The export holds only this workspace. Credentials, sealed values and encryption keys are never included."
      >
        <div className={styles.actions}>
          <Button busy={exporting} aria-disabled={exporting || undefined} onClick={() => void requestExport()}>
            Request export
          </Button>
        </div>
        {exportNote && (
          <p role="status" className={styles.note}>
            {exportNote}
          </p>
        )}
      </Section>

      <Section
        title="Delete this workspace"
        description="Deletes the workspace data and checks that none remains. Only an owner can do this, and it cannot be undone."
      >
        <div className={styles.danger}>
          <p className={styles.note}>
            The audit history is kept. It is append-only by database permissions, with a hash chain that detects casual
            edits; not tamper-resistant against a database superuser.
          </p>
          <TextField
            label={`Type ${CONFIRMATION} to confirm`}
            autoComplete="off"
            spellCheck={false}
            value={text}
            onChange={(event) => setText(event.target.value)}
          />
          <div className={styles.actions}>
            <Button
              variant="danger"
              busy={deleting}
              disabled={text !== CONFIRMATION || deleting}
              onClick={() => void remove()}
            >
              Delete workspace
            </Button>
          </div>
          {deleteNote && (
            <p role="status" className={styles.note}>
              {deleteNote}
            </p>
          )}
        </div>
      </Section>
    </>
  );
}
