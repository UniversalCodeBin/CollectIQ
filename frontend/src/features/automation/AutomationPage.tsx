// FILE GUIDE: settings (SCR-10 and its neighbours). One route, settings/:tab, with the section list beside the open
// panel. The automation panel lives here; the other panels are in features/settings and features/ai. Nothing on these
// screens can make CollectIQ send to a customer by itself: every message still needs a person to approve it.
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { type FormEvent, type ReactElement, useEffect, useState } from "react";
import { NavLink, useParams } from "react-router";
import { NotFoundPage } from "../../app/NotFoundPage";
import { Button } from "../../components/ui/Button";
import { Callout } from "../../components/ui/Callout";
import { fieldError, SelectField, TextField } from "../../components/ui/Field";
import { MutationFeedback } from "../../components/ui/MutationFeedback";
import { Page, PageHeader, Section } from "../../components/ui/Page";
import { QueryState } from "../../components/ui/QueryState";
import { ApiProblem, apiRequest, useApiMutation } from "../../lib/api";
import { formatDate } from "../../lib/format";
import { AiSettingsPanel } from "../ai/AiSettingsPanel";
import { BusinessPanel } from "../settings/BusinessPanel";
import { MembersPanel } from "../settings/MembersPanel";
import { NotificationsPanel } from "../settings/NotificationsPanel";
import { PayloadsPanel } from "../settings/PayloadsPanel";
import { PrivacyPanel } from "../settings/PrivacyPanel";
import styles from "../settings/Settings.module.css";

const refuse = (field: string, message: string) =>
  new ApiProblem({
    status: 400,
    code: "VALIDATION_FAILED",
    detail: "",
    correlationId: null,
    errors: [{ field, message }],
  });

/** Workspace-wide choices first, then AI, then the ones that are personal or final. */
const TABS = [
  ["business", "Your business"],
  ["members", "Members"],
  ["automation", "Automation"],
  ["ai", "AI assistance"],
  ["payloads", "Sent to AI"],
  ["notifications", "Notifications"],
  ["privacy", "Export and deletion"],
] as const;

export function AutomationPage() {
  const { tab, ws = "" } = useParams();
  const panels: Record<string, ReactElement> = {
    automation: <AutomationSettings />,
    ai: <AiSettingsPanel />,
    business: <BusinessPanel />,
    members: <MembersPanel />,
    notifications: <NotificationsPanel />,
    privacy: <PrivacyPanel />,
    payloads: <PayloadsPanel />,
  };
  const panel = tab ? panels[tab] : undefined;
  if (!panel) return <NotFoundPage />;

  return (
    <Page>
      <PageHeader title="Settings" description="How CollectIQ works for your business, your team and you." />
      <div className={styles.layout}>
        <nav aria-label="Settings sections" className={styles.nav}>
          <ul className={styles.navList}>
            {TABS.map(([key, label]) => (
              <li key={key}>
                <NavLink to={`/w/${ws}/settings/${key}`} className={styles.navLink}>
                  {label}
                </NavLink>
              </li>
            ))}
          </ul>
        </nav>
        <div className={styles.panel}>{panel}</div>
      </div>
    </Page>
  );
}

function AutomationSettings() {
  const { ws = "" } = useParams();
  const client = useQueryClient();
  const policy = useQuery({
    queryKey: ["policy", ws],
    queryFn: () => apiRequest({ method: "get", path: "/api/v1/workspaces/{ws}/policy" }, { path: { ws } }),
  });
  const versions = useQuery({
    queryKey: ["policy", ws, "versions"],
    queryFn: () => apiRequest({ method: "get", path: "/api/v1/workspaces/{ws}/policy/versions" }, { path: { ws } }),
  });
  const save = useApiMutation({ method: "put", path: "/api/v1/workspaces/{ws}/policy" }, { idempotent: true });
  const [mode, setMode] = useState("MANUAL");
  const [maxContacts, setMaxContacts] = useState("3");
  const [local, setLocal] = useState<ApiProblem | null>(null);
  const loaded = policy.data;
  const pending = save.status === "pending";

  useEffect(() => {
    if (!loaded) return;
    setMode(loaded.mode);
    const max = (loaded.limits as { max_contacts?: number }).max_contacts;
    if (typeof max === "number") setMaxContacts(String(max));
  }, [loaded]);

  useEffect(() => {
    if (save.status === "success") void client.invalidateQueries({ queryKey: ["policy", ws] });
  }, [save.status, client, ws]);

  function submit(event: FormEvent) {
    event.preventDefault();
    if (pending) return;
    const max = Number(maxContacts);
    if (!Number.isInteger(max) || max < 1 || max > 20) {
      return setLocal(refuse("max_contacts", "Enter a whole number from 1 to 20."));
    }
    setLocal(null);
    save.submit({ path: { ws }, body: { mode: mode as never, limits: { max_contacts: max } } });
  }

  return (
    <>
      <Section
        title="Automation"
        description="How much CollectIQ prepares for you, and how often one customer may be reminded."
      >
        <Callout tone="safe" title="CollectIQ never sends to a customer by itself">
          It prepares reminders and follow-ups and checks them for disputes, holds and limits. A person approves every
          message before it goes out.
        </Callout>
        <QueryState query={policy} label="automation settings">
          {loaded && (
            <form className={styles.form} onSubmit={submit} noValidate>
              <SelectField label="Mode" value={mode} onChange={(e) => setMode(e.target.value)}>
                <option value="MANUAL">Manual: I decide every step</option>
                <option value="ASSISTED">Assisted: CollectIQ prepares drafts for my approval</option>
              </SelectField>
              <TextField
                label="Most reminders to one customer"
                hint="A whole number from 1 to 20."
                inputMode="numeric"
                value={maxContacts}
                onChange={(e) => setMaxContacts(e.target.value)}
                error={fieldError(local, "max_contacts")}
              />
              <p className={styles.muted}>
                Automatic snoozing is {loaded.auto_snooze_available ? "available" : "not available yet"}. Every message
                to a customer still needs a person to approve it.
              </p>
              <MutationFeedback mutation={save} />
              {save.status === "success" && (
                <p role="status" className={styles.done}>
                  Settings saved.
                </p>
              )}
              <div className={styles.actions}>
                <Button variant="primary" type="submit" busy={pending} aria-disabled={pending || undefined}>
                  Save settings
                </Button>
              </div>
            </form>
          )}
        </QueryState>
      </Section>

      <QueryState query={versions} label="settings history">
        {versions.data && versions.data.items.length > 0 && (
          <Section title="Earlier versions" description="Each save keeps the previous settings." level={3}>
            <ul className={styles.history}>
              {versions.data.items.map((v) => (
                <li key={v.version}>
                  <span>
                    Version {v.version}: {v.mode === "MANUAL" ? "Manual" : "Assisted"}
                    {v.automation_paused ? ", automation paused" : ""}
                  </span>
                  <time className={styles.date} dateTime={v.effective_from}>
                    {formatDate(v.effective_from)}
                  </time>
                </li>
              ))}
            </ul>
          </Section>
        )}
      </QueryState>
    </>
  );
}
