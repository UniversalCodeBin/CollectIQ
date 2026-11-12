import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Bell,
  Building2,
  FileUp,
  LogOut,
  Menu as MenuIcon,
  MessageSquarePlus,
  PanelLeftClose,
  PanelLeftOpen,
  Plus,
  Receipt,
  Search,
  ShieldCheck,
  SlidersHorizontal,
  Users,
  X,
} from "lucide-react";
import { type FormEvent, type ReactNode, useEffect, useRef, useState } from "react";
import { Link, NavLink, useLocation, useNavigate } from "react-router";
import { BrandLockup } from "../components/ui/BrandMark";
import { IconButton } from "../components/ui/Button";
import { Menu, menuItemClass, menuSeparatorClass } from "../components/ui/Menu";
import { MutationFeedback } from "../components/ui/MutationFeedback";
import { OfflineBanner } from "../components/ui/OfflineBanner";
import { SampleDataBanner } from "../components/ui/SampleDataBanner";
import { PauseControl } from "../features/automation/PauseControl";
import { apiRequest, useApiMutation } from "../lib/api";
import { NAV_ITEMS, type NavItem } from "./nav";
import styles from "./Shell.module.css";

type Workspace = { id: string; name: string };

type Props = {
  workspaceId: string;
  workspaceName: string;
  /** Every workspace the person belongs to; more than one shows the switcher. */
  workspaces?: Workspace[];
  /** The signed-in address, shown in the profile menu. */
  email?: string;
  sampleData?: boolean;
  children: ReactNode;
};

const RAIL_KEY = "collectiq.sidebar";

function readRail(): boolean {
  try {
    return window.localStorage.getItem(RAIL_KEY) === "rail";
  } catch {
    return false;
  }
}

function writeRail(rail: boolean) {
  try {
    window.localStorage.setItem(RAIL_KEY, rail ? "rail" : "full");
  } catch {
    /* A blocked store only means the choice is not remembered. */
  }
}

const SECTIONS: { title: string; labels: NavItem["label"][] }[] = [
  {
    title: "Ledger navigation",
    labels: [
      "Dashboard",
      "Receivables",
      "Payment Reconciliation",
      "Conversations",
      "Disputes & Blockers",
      "Follow-ups",
      "Review Inbox",
    ],
  },
  { title: "Operations", labels: ["Integrations", "Payment Accounts"] },
  { title: "Governance", labels: ["Audit History", "Settings"] },
];

/** First-page unread count; "20+" when more pages exist and every item on this one is unread. */
function useUnread(workspaceId: string): string | null {
  const notes = useQuery({
    queryKey: ["notifications", workspaceId],
    queryFn: () =>
      apiRequest({ method: "get", path: "/api/v1/workspaces/{ws}/notifications" }, { path: { ws: workspaceId } }),
    retry: false,
  });
  if (!notes.data) return null;
  const unread = notes.data.items.filter((note) => !note.read_at).length;
  if (unread === 0) return null;
  return notes.data.next_cursor && unread === notes.data.items.length ? `${unread}+` : String(unread);
}

export function Shell({ workspaceId, workspaceName, workspaces = [], email, sampleData = false, children }: Props) {
  const navigate = useNavigate();
  const { pathname } = useLocation();
  const client = useQueryClient();
  const signOut = useApiMutation({ method: "post", path: "/api/v1/auth/logout" });
  const signOutAll = useApiMutation({ method: "post", path: "/api/v1/auth/logout" });
  const signedOut = signOut.status === "success" || signOutAll.status === "success";

  const [rail, setRail] = useState(readRail);
  const [drawer, setDrawer] = useState(false);
  const [query, setQuery] = useState("");
  const search = useRef<HTMLInputElement>(null);
  const drawerButton = useRef<HTMLButtonElement>(null);
  const sidebar = useRef<HTMLElement>(null);
  const unread = useUnread(workspaceId);
  const base = `/w/${workspaceId}`;

  useEffect(() => {
    if (!signedOut) return;
    void Promise.resolve(navigate("/login", { replace: true })).then(() => client.clear());
  }, [signedOut, client, navigate]);

  // A route change closes the mobile drawer.
  useEffect(() => setDrawer(false), [pathname]);

  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      const target = event.target as HTMLElement | null;
      const typing = target?.closest("input, textarea, select, [contenteditable='true']");
      if (event.key === "/" && !typing) {
        event.preventDefault();
        search.current?.focus();
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  useEffect(() => {
    if (!drawer) return;
    sidebar.current?.querySelector<HTMLElement>("a, button")?.focus();
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setDrawer(false);
        drawerButton.current?.focus();
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [drawer]);

  function onSearch(event: FormEvent) {
    event.preventDefault();
    const text = query.trim();
    if (text) void navigate(`${base}/receivables?q=${encodeURIComponent(text)}`);
  }

  function toggleRail() {
    setRail((current) => {
      writeRail(!current);
      return !current;
    });
  }

  const byLabel = new Map(NAV_ITEMS.map((item) => [item.label, item]));
  const onAutomation = pathname.startsWith(`${base}/settings/automation`);
  const switcher =
    workspaces.length > 1 ? (
      <label className={styles.workspace}>
        <Building2 size={16} aria-hidden="true" />
        <span className="visually-hidden">Workspace</span>
        <select
          value={workspaceId}
          onChange={(event) => void navigate(`/w/${event.target.value}/dashboard`)}
          className={styles.workspaceSelect}
        >
          {workspaces.map((workspace) => (
            <option key={workspace.id} value={workspace.id}>
              {workspace.name}
            </option>
          ))}
        </select>
      </label>
    ) : (
      <span className={styles.workspace} title="Workspace">
        <Building2 size={16} aria-hidden="true" />
        <span className={styles.workspaceName}>{workspaceName}</span>
      </span>
    );

  function navLink(item: NavItem) {
    const Icon = item.icon;
    const body = (
      <>
        <Icon size={18} aria-hidden="true" className={styles.linkIcon} />
        <span className={styles.linkText}>{item.label}</span>
        {item.label === "Review Inbox" && unread && (
          <span className={styles.count} aria-label={`${unread} unread`}>
            {unread}
          </span>
        )}
      </>
    );
    if (item.label === "Settings") {
      // Every settings tab except Automation, which has its own link under Operations.
      const active = pathname.startsWith(`${base}/settings/`) && !onAutomation;
      return (
        <li key={item.label}>
          <Link
            to={`${base}/${item.to}`}
            title={rail ? item.label : undefined}
            className={`${styles.link} ${active ? styles.active : ""}`}
            aria-current={active ? "page" : undefined}
          >
            {body}
          </Link>
        </li>
      );
    }
    return (
      <li key={item.label}>
        <NavLink
          to={`${base}/${item.to}`}
          title={rail ? item.label : undefined}
          className={({ isActive }) => `${styles.link} ${isActive ? styles.active : ""}`}
        >
          {body}
        </NavLink>
      </li>
    );
  }

  return (
    <div className={styles.shell} data-rail={rail || undefined} data-drawer={drawer || undefined}>
      <a href="#main" className={styles.skip}>
        Skip to content
      </a>
      <header className={styles.appbar}>
        <IconButton
          ref={drawerButton}
          label={drawer ? "Close navigation" : "Open navigation"}
          aria-expanded={drawer}
          aria-controls="app-sidebar"
          className={styles.drawerToggle}
          onClick={() => setDrawer((open) => !open)}
        >
          {drawer ? <X size={20} aria-hidden="true" /> : <MenuIcon size={20} aria-hidden="true" />}
        </IconButton>

        <Link to={`${base}/dashboard`} className={styles.brand}>
          <BrandLockup />
        </Link>

        <div className={styles.workspaceSlot}>{switcher}</div>

        <form className={styles.search} onSubmit={onSearch} role="search">
          <Search size={16} aria-hidden="true" className={styles.searchIcon} />
          <input
            ref={search}
            type="search"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search invoices, customers, references…"
            aria-label="Search receivables"
            className={styles.searchInput}
          />
          <kbd className={styles.kbd} aria-hidden="true">
            /
          </kbd>
        </form>

        <div className={styles.actions}>
          <Menu
            triggerClassName={styles.add}
            triggerLabel="Add"
            trigger={
              <>
                <Plus size={16} aria-hidden="true" />
                <span className={styles.addText}>Add</span>
              </>
            }
          >
            <Link role="menuitem" to={`${base}/import/invoices`} className={menuItemClass}>
              <FileUp size={16} aria-hidden="true" />
              <span>
                <strong>Import invoices</strong>
                <span className={styles.itemSub}>From a CSV file or a PDF</span>
              </span>
            </Link>
            <Link role="menuitem" to={`${base}/reconciliation/unmatched`} className={menuItemClass}>
              <Receipt size={16} aria-hidden="true" />
              <span>
                <strong>Record a payment</strong>
                <span className={styles.itemSub}>Money you can see in your bank</span>
              </span>
            </Link>
            <Link role="menuitem" to={`${base}/conversations`} className={menuItemClass}>
              <MessageSquarePlus size={16} aria-hidden="true" />
              <span>
                <strong>Add a customer reply</strong>
                <span className={styles.itemSub}>Kept as their statement, never as proof</span>
              </span>
            </Link>
          </Menu>

          <Link
            to={`${base}/inbox`}
            className={styles.iconLink}
            aria-label={unread ? `Notifications, ${unread} unread` : "Notifications"}
            title="Notifications"
          >
            <Bell size={20} aria-hidden="true" />
            {unread && (
              <span className={styles.dot} aria-hidden="true">
                {unread}
              </span>
            )}
          </Link>

          <Menu
            triggerClassName={styles.profile}
            triggerLabel={email ? `Account menu for ${email}` : "Account menu"}
            trigger={
              <span className={styles.avatar} aria-hidden="true">
                {(email ?? "?").charAt(0).toUpperCase()}
              </span>
            }
            header={
              email ? (
                <>
                  <span className={styles.menuLabel}>Signed in as</span>
                  <strong>{email}</strong>
                </>
              ) : undefined
            }
          >
            <Link role="menuitem" to={`${base}/settings/business`} className={menuItemClass}>
              <SlidersHorizontal size={16} aria-hidden="true" />
              <span>Workspace settings</span>
            </Link>
            <Link role="menuitem" to={`${base}/settings/members`} className={menuItemClass}>
              <Users size={16} aria-hidden="true" />
              <span>Members</span>
            </Link>
            <span className={menuSeparatorClass} role="separator" />
            <button
              type="button"
              role="menuitem"
              className={menuItemClass}
              disabled={signOutAll.status === "pending"}
              onClick={() => signOutAll.submit({ query: { scope: "all" } })}
            >
              <LogOut size={16} aria-hidden="true" />
              <span>Sign out on every device</span>
            </button>
          </Menu>

          <button
            type="button"
            className={styles.signOut}
            disabled={signOut.status === "pending"}
            onClick={() => signOut.submit({})}
          >
            <LogOut size={18} aria-hidden="true" />
            <span className={styles.signOutText}>Sign out</span>
          </button>
        </div>
      </header>

      <div className={styles.scrim} aria-hidden="true" onClick={() => setDrawer(false)} />

      <aside id="app-sidebar" aria-label="Workspace navigation" ref={sidebar} className={styles.sidebar}>
        <div className={styles.drawerHead}>
          <BrandLockup />
          <IconButton
            label="Close navigation"
            onClick={() => {
              setDrawer(false);
              drawerButton.current?.focus();
            }}
          >
            <X size={20} aria-hidden="true" />
          </IconButton>
        </div>
        {drawer ? <div className={styles.drawerWorkspace}>{switcher}</div> : null}
        <nav aria-label="Main" className={styles.nav}>
          {SECTIONS.map((section) => (
            <div key={section.title} className={styles.section}>
              <h2 className={styles.sectionTitle}>{section.title}</h2>
              <ul className={styles.list}>
                {section.labels.map((label) => {
                  const item = byLabel.get(label);
                  return item ? navLink(item) : null;
                })}
                {section.title === "Operations" && (
                  <li>
                    <NavLink
                      to={`${base}/settings/automation`}
                      title={rail ? "Automation" : undefined}
                      className={({ isActive }) => `${styles.link} ${isActive ? styles.active : ""}`}
                    >
                      <ShieldCheck size={18} aria-hidden="true" className={styles.linkIcon} />
                      <span className={styles.linkText}>Automation</span>
                    </NavLink>
                  </li>
                )}
              </ul>
            </div>
          ))}
        </nav>
        <div className={styles.sidebarFoot}>
          <p className={styles.safety}>Nothing is sent to a customer until a person approves it.</p>
          <button
            type="button"
            className={styles.railToggle}
            aria-pressed={rail}
            onClick={toggleRail}
            title={rail ? "Expand sidebar" : "Collapse sidebar"}
          >
            {rail ? <PanelLeftOpen size={18} aria-hidden="true" /> : <PanelLeftClose size={18} aria-hidden="true" />}
            <span className={styles.linkText}>Collapse sidebar</span>
          </button>
        </div>
      </aside>

      <div className={styles.column}>
        <OfflineBanner />
        {sampleData && <SampleDataBanner />}
        <PauseControl workspace={workspaceId} />
        <MutationFeedback mutation={signOut} />
        <MutationFeedback mutation={signOutAll} />
        <main id="main" tabIndex={-1} className={styles.main}>
          {children}
        </main>
      </div>
    </div>
  );
}
