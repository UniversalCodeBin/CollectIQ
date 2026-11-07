import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useParams } from "react-router";
import { Button } from "../../components/ui/Button";
import { MutationFeedback } from "../../components/ui/MutationFeedback";
import { QueryState } from "../../components/ui/QueryState";
import { apiRequest, useApiMutation } from "../../lib/api";
import styles from "../automation/Automation.module.css";

type Flags = {
  pdf_extraction_enabled: boolean;
  reply_interpretation_enabled: boolean;
  invoice_brief_enabled: boolean;
  kill_switch: boolean;
};
const OFF: Flags = { pdf_extraction_enabled: false, reply_interpretation_enabled: false, invoice_brief_enabled: false, kill_switch: false };

/** AI opt-ins (E109, E110). Everything is off until an Owner turns it on; the kill switch overrides all. */
export function AiSettingsPanel() {
  const { ws = "" } = useParams();
  const client = useQueryClient();
  const settings = useQuery({
    queryKey: ["ai-settings", ws],
    queryFn: () => apiRequest({ method: "get", path: "/api/v1/workspaces/{ws}/ai/settings" }, { path: { ws } }),
  });
  const save = useApiMutation({ method: "put", path: "/api/v1/workspaces/{ws}/ai/settings" }, { idempotent: true });
  const [flags, setFlags] = useState<Flags>(OFF);
  const loaded = settings.data;

  useEffect(() => {
    if (loaded)
      setFlags({
        pdf_extraction_enabled: loaded.pdf_extraction_enabled,
        reply_interpretation_enabled: loaded.reply_interpretation_enabled,
        invoice_brief_enabled: loaded.invoice_brief_enabled,
        kill_switch: loaded.kill_switch,
      });
  }, [loaded]);
  useEffect(() => {
    if (save.status === "success") void client.invalidateQueries({ queryKey: ["ai-settings", ws] });
  }, [save.status, client, ws]);

  const toggle = (name: keyof Flags, label: string, hint: string) => (
    <label key={name} className={styles.muted} style={{ display: "grid", gap: "var(--space-1)" }}>
      <span>
        <input type="checkbox" checked={flags[name]} onChange={(e) => setFlags({ ...flags, [name]: e.target.checked })} /> {label}
      </span>
      <span>{hint}</span>
    </label>
  );

  return (
    <div className={styles.page}>
      <h1 className={styles.title}>AI assistance</h1>
      <QueryState query={settings} label="AI settings">
        {loaded && (
          <form
            className={styles.card}
            onSubmit={(event) => {
              event.preventDefault();
              save.submit({ path: { ws }, body: flags });
            }}
          >
            {!loaded.provider_configured && (
              <p role="status">AI is not configured on this server, so these options have no effect yet. CSV import and manual entry work as usual.</p>
            )}
            <p className={styles.muted}>
              Off by default. When on, only the text of a document or reply, with email addresses, phone numbers and long digit runs masked,
              goes to the configured AI provider. Anything the AI reads is shown as unverified until a person confirms it. It never sends a
              message, marks anything paid or allocates a payment.
            </p>
            {toggle("pdf_extraction_enabled", "Allow AI to read uploaded invoice PDFs", "You review and confirm every field before an invoice is created.")}
            {toggle("reply_interpretation_enabled", "Allow AI to interpret customer replies", "A person can accept, correct or dismiss each reading.")}
            {toggle("invoice_brief_enabled", "Allow AI invoice briefs", "A short summary and draft wording for one invoice. Nothing is sent; you review any wording first.")}
            {toggle("kill_switch", "Stop all AI processing now", "Overrides the options above until you turn it off.")}
            <MutationFeedback mutation={save} />
            <div className={styles.actions}>
              <Button variant="primary" type="submit" aria-disabled={save.status === "pending" || undefined}>
                Save AI settings
              </Button>
            </div>
          </form>
        )}
      </QueryState>
    </div>
  );
}
