import { useQueryClient } from "@tanstack/react-query";
import { type ReactNode, useEffect } from "react";
import { NavLink, useNavigate } from "react-router";
import { Button } from "../components/ui/Button";
import { MutationFeedback } from "../components/ui/MutationFeedback";
import { OfflineBanner } from "../components/ui/OfflineBanner";
import { SampleDataBanner } from "../components/ui/SampleDataBanner";
import { useApiMutation } from "../lib/api";
import { NAV_ITEMS } from "./nav";
import styles from "./Shell.module.css";

type Props = {
  workspaceId: string;
  workspaceName: string;
  sampleData?: boolean;
  children: ReactNode;
};

export function Shell({ workspaceId, workspaceName, sampleData = false, children }: Props) {
  const navigate = useNavigate();
  const signOut = useApiMutation({ method: "post", path: "/api/v1/auth/logout" });
  const client = useQueryClient();
  const signedOut = signOut.status === "success";

  useEffect(() => {
    if (!signedOut) return;
    // Everything cached belonged to the person leaving. Cleared after the move so this page never refetches it.
    void Promise.resolve(navigate("/login", { replace: true })).then(() => client.clear());
  }, [signedOut, client, navigate]);

  return (
    <div className={styles.shell} data-has-nav={NAV_ITEMS.length > 0 || undefined}>
      <a href="#main" className={styles.skip}>
        Skip to content
      </a>
      <header className={styles.header}>
        <span className={styles.brand}>CollectIQ</span>
        <span className={styles.workspace}>{workspaceName}</span>
        <Button variant="quiet" onClick={() => signOut.submit({})}>
          Sign out
        </Button>
      </header>
      {NAV_ITEMS.length > 0 && (
        <nav aria-label="Main" className={styles.nav}>
          {NAV_ITEMS.map(({ label, to, icon: Icon }) => (
            <NavLink key={label} to={`/w/${workspaceId}/${to}`} className={styles.link}>
              <Icon size={20} aria-hidden="true" />
              <span className={styles.linkText}>{label}</span>
            </NavLink>
          ))}
        </nav>
      )}
      <div className={styles.column}>
        <OfflineBanner />
        {sampleData && <SampleDataBanner />}
        <MutationFeedback mutation={signOut} />
        <main id="main" tabIndex={-1} className={styles.main}>
          {children}
        </main>
      </div>
    </div>
  );
}
