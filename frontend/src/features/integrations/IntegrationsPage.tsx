// FILE GUIDE: integrations (SCR-16, E093–E097, E129). What the product can honestly list (integrations/registry.py): provider
// connections, which show as connected only after a verification succeeded, and file-based or manual paths, which are
// never connections. Connecting Gmail sends the person to Google to approve; connecting PayPal verifies API credentials.
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useParams } from "react-router";
import { Button } from "../../components/ui/Button";
import { Callout } from "../../components/ui/Callout";
import { TextField } from "../../components/ui/Field";
import { MutationFeedback } from "../../components/ui/MutationFeedback";
import { Page, PageHeader, Section } from "../../components/ui/Page";
import { QueryState } from "../../components/ui/QueryState";
import { apiRequest, useApiMutation } from "../../lib/api";
import type { components } from "../../lib/api-types";
import { formatDate } from "../../lib/format";
import styles from "./Integrations.module.css";

type Integration = components["schemas"]["IntegrationItemOut"] & {
  environment?: string | null;
  external_account?: string | null;
  webhook_status?: string | null;
  last_event_received_at?: string | null;
  last_event_status?: string | null;
};

const STATE_TEXT: Record<string, string> = {
  FILE_BASED: "File based",
  MANUAL: "Manual",
  NEEDS_CONFIGURATION: "Needs configuration",
  SANDBOX_ONLY: "Sandbox only",
  CONNECTED_VERIFIED: "Connected and verified",
  NEEDS_REAUTH: "Needs re-authorization",
  DEGRADED: "Degraded",
  DISCONNECTED: "Disconnected",
};

function getPayPalMeaningfulStatus(item: Integration): string {
  if (item.state === "CONNECTED_VERIFIED") return "Connected and verified";
  if (item.state === "SANDBOX_ONLY") return "Sandbox only";
  if (item.last_error) {
    const err = item.last_error.toLowerCase();
    if (err.includes("credential") || err.includes("missing")) return "Credentials missing";
    if (err.includes("auth") || err.includes("401")) return "Authentication failed";
    if (err.includes("webhook")) return "Webhook not registered";
    if (err.includes("unreachable") || err.includes("unavailable") || err.includes("timeout")) return "Provider unavailable";
    if (err.includes("config")) return "Configuration error";
  }
  if (item.state === "NEEDS_CONFIGURATION") return "Not configured";
  if (item.state === "NEEDS_REAUTH") return "Needs re-authorization";
  return STATE_TEXT[item.state] ?? item.state;
}

/** Connect (E094) sends the person to Google to approve; Disconnect (E097) revokes. Neither sends any message. */
function GmailActions({ ws, connected }: { ws: string; connected: boolean }) {
  const client = useQueryClient();
  const connect = useApiMutation({ method: "post", path: "/api/v1/workspaces/{ws}/integrations/gmail/connect" });
  const disconnect = useApiMutation(
    { method: "delete", path: "/api/v1/workspaces/{ws}/integrations/{key}" },
    { idempotent: true },
  );
  const url = connect.data?.authorization_url;
  const connecting = connect.status === "pending" || Boolean(url);

  useEffect(() => {
    if (url) window.location.assign(url);
  }, [url]);

  useEffect(() => {
    if (disconnect.status === "success") void client.invalidateQueries({ queryKey: ["integrations", ws] });
  }, [disconnect.status, client, ws]);

  return (
    <div className={styles.controls}>
      <MutationFeedback mutation={connect} />
      <MutationFeedback mutation={disconnect} />
      <div className={styles.actions}>
        {connected ? (
          <Button
            variant="secondary"
            busy={disconnect.status === "pending"}
            aria-disabled={disconnect.status === "pending" || undefined}
            onClick={() => disconnect.status !== "pending" && disconnect.submit({ path: { ws, key: "GMAIL" } })}
          >
            Disconnect Gmail
          </Button>
        ) : (
          <Button
            variant="primary"
            busy={connecting}
            aria-disabled={connecting || undefined}
            onClick={() => !connecting && connect.submit({ path: { ws } })}
          >
            Connect Gmail
          </Button>
        )}
      </div>
      <p className={styles.muted}>
        {connected
          ? "Disconnecting stops sending from CollectIQ. Approved reminders can still be sent by hand and recorded."
          : "You approve access on Google's own page. Connecting sends nothing; each reminder still needs a person to approve and send it."}
      </p>
    </div>
  );
}

/** PayPal Sandbox integration controls, verification, status and live disconnect. */
function PayPalActions({ ws, item }: { ws: string; item: Integration }) {
  const client = useQueryClient();
  const [merchantId, setMerchantId] = useState(item.external_account || "");

  const verify = useApiMutation(
    { method: "post", path: "/api/v1/workspaces/{ws}/integrations/paypal/connect" },
    { idempotent: true },
  );

  const disconnect = useApiMutation(
    { method: "delete", path: "/api/v1/workspaces/{ws}/integrations/{key}" },
    { idempotent: true },
  );

  useEffect(() => {
    if (verify.status === "success" || disconnect.status === "success") {
      void client.invalidateQueries({ queryKey: ["integrations", ws] });
    }
  }, [verify.status, disconnect.status, client, ws]);

  const isConnected = item.state === "CONNECTED_VERIFIED";
  const envLabel = item.environment ? item.environment.toUpperCase() : "SANDBOX";

  return (
    <div className={styles.controls}>
      <div className={styles.sandboxBadge}>
        <span>Environment: {envLabel}</span>
      </div>

      <p className={styles.muted}>
        Sandbox Mode: All transactions are processed using PayPal test endpoints. No real funds are moved.
      </p>

      <div className={styles.detailsGrid}>
        <div className={styles.detailItem}>
          <span className={styles.detailLabel}>Verification Status</span>
          <span className={styles.detailValue}>{getPayPalMeaningfulStatus(item)}</span>
        </div>
        <div className={styles.detailItem}>
          <span className={styles.detailLabel}>Webhook Status</span>
          <span className={styles.detailValue}>{item.webhook_status || "Not registered"}</span>
        </div>
        <div className={styles.detailItem}>
          <span className={styles.detailLabel}>Last Verified</span>
          <span className={styles.detailValue}>
            {item.verified_at ? formatDate(item.verified_at) : "Never"}
          </span>
        </div>
        <div className={styles.detailItem}>
          <span className={styles.detailLabel}>Last Event</span>
          <span className={styles.detailValue}>
            {item.last_event_received_at ? formatDate(item.last_event_received_at) : "None yet"}
          </span>
        </div>
      </div>

      {item.last_error && (
        <Callout tone="error" title="Verification Notice">
          {item.last_error}
        </Callout>
      )}

      <MutationFeedback mutation={verify} />
      <MutationFeedback mutation={disconnect} />

      <form
        className={styles.connectForm}
        onSubmit={(e) => {
          e.preventDefault();
          if (verify.status !== "pending") {
            const trimmed = merchantId.trim();
            verify.submit({
              path: { ws },
              body: trimmed ? { merchant_id: trimmed } : ({} as any),
            });
          }
        }}
      >
        <div className={styles.inputWrapper}>
          <TextField
            label="PayPal Merchant ID"
            value={merchantId}
            onChange={(e) => setMerchantId(e.target.value)}
            placeholder="e.g. FAKEMERCHANT1 or SB_MERCHANT_ID"
            hint="Associated PayPal Business Account merchant identifier."
          />
        </div>
        <div className={styles.actions}>
          <Button
            variant="primary"
            type="submit"
            busy={verify.status === "pending"}
            aria-disabled={verify.status === "pending" || undefined}
          >
            Verify connection
          </Button>
          {isConnected && (
            <Button
              variant="secondary"
              type="button"
              busy={disconnect.status === "pending"}
              aria-disabled={disconnect.status === "pending" || undefined}
              onClick={() => disconnect.status !== "pending" && disconnect.submit({ path: { ws, key: "PAYPAL" } })}
            >
              Disconnect PayPal
            </Button>
          )}
        </div>
      </form>
    </div>
  );
}

function IntegrationRow({ ws, item }: { ws: string; item: Integration }) {
  const meaningfulStatus = item.key === "PAYPAL" ? getPayPalMeaningfulStatus(item) : (STATE_TEXT[item.state] ?? item.state);
  const verified = item.kind === "PROVIDER" && item.state === "CONNECTED_VERIFIED";

  return (
    <li className={styles.item}>
      <div className={styles.itemHead}>
        <h3 className={styles.label}>{item.label}</h3>
        <span className={styles.state} data-state={item.state}>
          {meaningfulStatus}
        </span>
      </div>
      {item.note && !verified && <p className={styles.note}>{item.note}</p>}
      {item.verified_at && (
        <p className={styles.muted}>
          Verified{" "}
          <time className={styles.date} dateTime={item.verified_at}>
            {formatDate(item.verified_at)}
          </time>
        </p>
      )}
      {item.last_error && item.key !== "PAYPAL" && (
        <p role="status" className={styles.error}>
          {item.last_error}
        </p>
      )}
      {item.key === "GMAIL" && <GmailActions ws={ws} connected={item.state === "CONNECTED_VERIFIED"} />}
      {item.key === "PAYPAL" && <PayPalActions ws={ws} item={item} />}
    </li>
  );
}

export function IntegrationsPage() {
  const { ws = "" } = useParams();
  const list = useQuery({
    queryKey: ["integrations", ws],
    queryFn: () => apiRequest({ method: "get", path: "/api/v1/workspaces/{ws}/integrations" }, { path: { ws } }),
  });
  const items = list.data?.items ?? [];
  const providers = items.filter((item) => item.kind === "PROVIDER");
  const paths = items.filter((item) => item.kind !== "PROVIDER");

  return (
    <Page>
      <PageHeader
        title="Integrations"
        description="How invoices, statements and messages get in and out of CollectIQ. Your accounting system stays the record; CollectIQ works alongside it."
      />

      <QueryState query={list} label="integrations">
        {providers.length > 0 && (
          <Section
            title="Connections"
            description="A connection shows as connected only after CollectIQ has verified it with the provider."
          >
            <ul className={styles.list}>
              {providers.map((item) => (
                <IntegrationRow key={item.key} ws={ws} item={item} />
              ))}
            </ul>
          </Section>
        )}
        {paths.length > 0 && (
          <Section
            title="Files and manual steps"
            description="These work without connecting anything. They are never shown as connected."
          >
            <ul className={styles.list}>
              {paths.map((item) => (
                <IntegrationRow key={item.key} ws={ws} item={item} />
              ))}
            </ul>
          </Section>
        )}
      </QueryState>
    </Page>
  );
}
