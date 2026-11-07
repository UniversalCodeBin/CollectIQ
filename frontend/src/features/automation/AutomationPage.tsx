import { useQuery, useQueryClient } from "@tanstack/react-query";
import { type FormEvent, type ReactElement, useEffect, useState } from "react";
import { NavLink, useParams } from "react-router";
import { Button } from "../../components/ui/Button";
import { fieldError, SelectField, TextField } from "../../components/ui/Field";
import { MutationFeedback } from "../../components/ui/MutationFeedback";
import { QueryState } from "../../components/ui/QueryState";
import { ApiProblem, apiRequest, useApiMutation } from "../../lib/api";
import { formatDate } from "../../lib/format";
import { NotFoundPage } from "../../app/NotFoundPage";
import { AiSettingsPanel } from "../ai/AiSettingsPanel";
import { BusinessPanel } from "../settings/BusinessPanel";
import { MembersPanel } from "../settings/MembersPanel";
import { NotificationsPanel } from "../settings/NotificationsPanel";
import { PayloadsPanel } from "../settings/PayloadsPanel";
import { PrivacyPanel } from "../settings/PrivacyPanel";
import styles from "./Automation.module.css";

const refuse = (field: string, message: string) =>
  new ApiProblem({
    status: 400,
    code: "VALIDATION_FAILED",
    detail: "",
    correlationId: null,
    errors: [{ field, message }],
  });

const TABS = [
  ["automation", "Automation"],
  ["ai", "AI"],
  ["business", "Your business"],
  ["members", "Members"],
  ["notifications", "Notifications"],
  ["privacy", "Export and deletion"],
  ["payloads", "AI payloads"],
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
    <>
      <nav aria-label="Settings sections">
        <ul
          style={{
            display: "flex",
            flexWrap: "wrap",
            gap: "1rem",
            listStyle: "none",
            padding: 0,
          }}
        >
          {TABS.map(([key, label]) => (
            <li key={key}>
              <NavLink to={`/w/${ws}/settings/${key}`}>{label}</NavLink>
            </li>
          ))}
        </ul>
      </nav>
      {panel}
    </>
  );
}

function AutomationSettings() {
  const { ws = "" } = useParams();
  const client = useQueryClient();
  const policy = useQuery({
    queryKey: ["policy", ws],
    queryFn: () =>
      apiRequest(
        { method: "get", path: "/api/v1/workspaces/{ws}/policy" },
        { path: { ws } },
      ),
  });
  const versions = useQuery({
    queryKey: ["policy", ws, "versions"],
    queryFn: () =>
      apiRequest(
        { method: "get", path: "/api/v1/workspaces/{ws}/policy/versions" },
        { path: { ws } },
      ),
  });
  const save = useApiMutation(
    { method: "put", path: "/api/v1/workspaces/{ws}/policy" },
    { idempotent: true },
  );
  const [mode, setMode] = useState("MANUAL");
  const [maxContacts, setMaxContacts] = useState("3");
  const [local, setLocal] = useState<ApiProblem | null>(null);
  const loaded = policy.data;

  useEffect(() => {
    if (!loaded) return;
    setMode(loaded.mode);
    const max = (loaded.limits as { max_contacts?: number }).max_contacts;
    if (typeof max === "number") setMaxContacts(String(max));
  }, [loaded]);

  useEffect(() => {
    if (save.status === "success")
      void client.invalidateQueries({ queryKey: ["policy", ws] });
  }, [save.status, client, ws]);

  function submit(event: FormEvent) {
    event.preventDefault();
    const max = Number(maxContacts);
    if (!Number.isInteger(max) || max < 1 || max > 20) {
      return setLocal(
        refuse("max_contacts", "Enter a whole number from 1 to 20."),
      );
    }
    setLocal(null);
    save.submit({
      path: { ws },
      body: { mode: mode as never, limits: { max_contacts: max } },
    });
  }

  return (
    <div className={styles.page}>
      <h1 className={styles.title}>Automation settings</h1>
      <QueryState query={policy} label="automation settings">
        {loaded && (
          <form className={styles.card} onSubmit={submit} noValidate>
            <SelectField
              label="Mode"
              value={mode}
              onChange={(e) => setMode(e.target.value)}
            >
              <option value="MANUAL">Manual: I decide every step</option>
              <option value="ASSISTED">
                Assisted: CollectIQ prepares drafts for my approval
              </option>
            </SelectField>
            <TextField
              label="Most reminders to one customer"
              inputMode="numeric"
              value={maxContacts}
              onChange={(e) => setMaxContacts(e.target.value)}
              error={fieldError(local, "max_contacts")}
            />
            <p className={styles.muted}>
              Automatic snoozing is{" "}
              {loaded.auto_snooze_available ? "available" : "not available yet"}
              . Every message to a customer still needs a person to approve it.
            </p>
            <MutationFeedback mutation={save} />
            <div className={styles.actions}>
              <Button
                variant="primary"
                type="submit"
                aria-disabled={save.status === "pending" || undefined}
              >
                Save settings
              </Button>
            </div>
          </form>
        )}
      </QueryState>
      <QueryState query={versions} label="settings history">
        <h2>History</h2>
        <ul className={styles.list}>
          {versions.data?.items.map((v) => (
            <li key={v.version} className={styles.muted}>
              {`Version ${v.version} · ${v.mode === "MANUAL" ? "Manual" : "Assisted"}${v.automation_paused ? " · paused" : ""} · ${formatDate(v.effective_from)}`}
            </li>
          ))}
        </ul>
      </QueryState>
    </div>
  );
}
