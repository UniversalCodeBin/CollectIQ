import { useQueryClient } from "@tanstack/react-query";
import { type FormEvent, useEffect, useMemo, useState } from "react";
import { Navigate, useNavigate, useParams } from "react-router";
import { NotFoundPage } from "../../app/NotFoundPage";
import { SESSION_KEY, SessionGate } from "../../app/SessionGate";
import { Button } from "../../components/ui/Button";
import { fieldError, SelectField, TextField } from "../../components/ui/Field";
import { MutationFeedback } from "../../components/ui/MutationFeedback";
import { useApiMutation } from "../../lib/api";
import { AuthPage, authStyles } from "../auth/AuthPage";

const COUNTRIES = [
  ["IN", "India"],
  ["US", "United States"],
  ["GB", "United Kingdom"],
  ["SG", "Singapore"],
  ["AE", "United Arab Emirates"],
  ["CA", "Canada"],
  ["AU", "Australia"],
] as const;

const CURRENCIES = [
  ["INR", "Indian rupee (₹)"],
  ["USD", "US dollar ($)"],
] as const;

function WorkspaceStep() {
  const browserZone = useMemo(() => Intl.DateTimeFormat().resolvedOptions().timeZone, []);
  const zones = useMemo(() => [...new Set([browserZone, ...Intl.supportedValuesOf("timeZone")])], [browserZone]);
  const [name, setName] = useState("");
  const [country, setCountry] = useState("IN");
  const [timezone, setTimezone] = useState(browserZone);
  const [currency, setCurrency] = useState("INR");
  const navigate = useNavigate();
  const client = useQueryClient();
  const create = useApiMutation({ method: "post", path: "/api/v1/workspaces" }, { idempotent: true });
  const created = create.status === "success" ? create.data?.id : undefined;

  useEffect(() => {
    if (!created) return;
    void client.invalidateQueries({ queryKey: SESSION_KEY }).then(() => {
      void navigate(`/w/${created}/dashboard`, { replace: true });
    });
  }, [created, client, navigate]);

  function submit(event: FormEvent) {
    event.preventDefault();
    create.submit({ body: { name, country, timezone, default_currency: currency } });
  }

  return (
    <AuthPage title="Set up your workspace">
      <form className={authStyles.form} onSubmit={submit}>
        <TextField
          label="Business name"
          name="organization"
          autoComplete="organization"
          required
          value={name}
          onChange={(event) => setName(event.target.value)}
          error={fieldError(create.problem, "name")}
        />
        <SelectField
          label="Country or region"
          value={country}
          onChange={(event) => setCountry(event.target.value)}
          error={fieldError(create.problem, "country")}
        >
          {COUNTRIES.map(([code, label]) => (
            <option key={code} value={code}>
              {label}
            </option>
          ))}
        </SelectField>
        <SelectField
          label="Timezone"
          hint="We filled this in from your browser. Reminders and due dates use it, so check it's right."
          value={timezone}
          onChange={(event) => setTimezone(event.target.value)}
          error={fieldError(create.problem, "timezone")}
        >
          {zones.map((zone) => (
            <option key={zone} value={zone}>
              {zone}
            </option>
          ))}
        </SelectField>
        <SelectField
          label="Default currency"
          hint="You can still record invoices in other currencies."
          value={currency}
          onChange={(event) => setCurrency(event.target.value)}
          error={fieldError(create.problem, "default_currency")}
        >
          {CURRENCIES.map(([code, label]) => (
            <option key={code} value={code}>
              {label}
            </option>
          ))}
        </SelectField>
        <MutationFeedback mutation={create} />
        {create.status !== "unknown" && (
          <Button type="submit" variant="primary" disabled={create.status === "pending" || Boolean(created)}>
            Create workspace
          </Button>
        )}
      </form>
    </AuthPage>
  );
}

export function OnboardingPage() {
  const { step } = useParams();
  if (step !== "workspace") return <NotFoundPage />;
  return (
    <SessionGate>
      {(session) =>
        session.user.email_verified ? (
          <WorkspaceStep />
        ) : (
          <Navigate to="/verify-email" replace state={{ email: session.user.email }} />
        )
      }
    </SessionGate>
  );
}
