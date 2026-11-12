import { useQuery, useQueryClient } from "@tanstack/react-query";
import { type FormEvent, useEffect, useState } from "react";
import { useParams } from "react-router";
import { Button } from "../../components/ui/Button";
import { Callout } from "../../components/ui/Callout";
import { Checkbox } from "../../components/ui/Field";
import { MutationFeedback } from "../../components/ui/MutationFeedback";
import { Section } from "../../components/ui/Page";
import { QueryState } from "../../components/ui/QueryState";
import { apiRequest, useApiMutation } from "../../lib/api";
import styles from "../settings/Settings.module.css";

type Flags = {
  pdf_extraction_enabled: boolean;
  reply_interpretation_enabled: boolean;
  invoice_brief_enabled: boolean;
  kill_switch: boolean;
};
const OFF: Flags = {
  pdf_extraction_enabled: false,
  reply_interpretation_enabled: false,
  invoice_brief_enabled: false,
  kill_switch: false,
};

const OPT_INS: { name: keyof Flags; label: string; hint: string }[] = [
  {
    name: "pdf_extraction_enabled",
    label: "Allow AI to read uploaded invoice PDFs",
    hint: "You review and confirm every field before an invoice is created.",
  },
  {
    name: "reply_interpretation_enabled",
    label: "Allow AI to interpret customer replies",
    hint: "A person can accept, correct or dismiss each reading.",
  },
  {
    name: "invoice_brief_enabled",
    label: "Allow AI invoice briefs",
    hint: "A short summary and draft wording for one invoice. Nothing is sent; you review any wording first.",
  },
];

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
  const pending = save.status === "pending";

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

  function submit(event: FormEvent) {
    event.preventDefault();
    if (pending) return;
    save.submit({ path: { ws }, body: flags });
  }

  const set = (name: keyof Flags, on: boolean) => setFlags((current) => ({ ...current, [name]: on }));

  return (
    <Section
      title="AI assistance"
      description="Off by default. When on, only the text of a document or reply, with email addresses, phone numbers and long digit runs masked, goes to the configured AI provider. Anything the AI reads is shown as unverified until a person confirms it. It never sends a message, marks anything paid or allocates a payment."
    >
      <QueryState query={settings} label="AI settings">
        {loaded && (
          <form className={`${styles.form} ${styles.formWide}`} onSubmit={submit} noValidate>
            {!loaded.provider_configured && (
              <Callout tone="info" role="status">
                AI is not configured on this server, so these options have no effect yet. CSV import and manual entry
                work as usual.
              </Callout>
            )}
            <fieldset className={styles.fieldset}>
              <legend className={styles.legend}>What AI may help with</legend>
              {OPT_INS.map((option) => (
                <Checkbox
                  key={option.name}
                  label={option.label}
                  hint={option.hint}
                  checked={flags[option.name]}
                  onChange={(event) => set(option.name, event.target.checked)}
                />
              ))}
            </fieldset>
            <div className={styles.stop}>
              <Checkbox
                label="Stop all AI processing now"
                hint="Overrides the options above until you turn it off."
                checked={flags.kill_switch}
                onChange={(event) => set("kill_switch", event.target.checked)}
              />
            </div>
            <MutationFeedback mutation={save} />
            {save.status === "success" && (
              <p role="status" className={styles.done}>
                AI settings saved.
              </p>
            )}
            <div className={styles.actions}>
              <Button variant="primary" type="submit" busy={pending} aria-disabled={pending || undefined}>
                Save AI settings
              </Button>
            </div>
          </form>
        )}
      </QueryState>
    </Section>
  );
}
