import { History, Inbox, Landmark, Plug, LayoutDashboard, List, MessagesSquare, Scale, Send, Settings, ShieldAlert, type LucideIcon } from "lucide-react";

export const DIRECTIVE_NAV = [
  "Dashboard",
  "Receivables",
  "Payment Reconciliation",
  "Conversations",
  "Disputes & Blockers",
  "Follow-ups",
  "Review Inbox",
  "Integrations",
  "Payment Accounts",
  "Audit History",
  "Settings",
] as const;

export type NavItem = {
  label: (typeof DIRECTIVE_NAV)[number];
  /** The key of the built screen in router.tsx. */
  route: string;
  /** Where the link goes, relative to /w/:ws. */
  to: string;
  icon: LucideIcon;
};

/** Each task that builds a screen adds its item here, in directive order, so no link is ever dead. */
export const NAV_ITEMS: NavItem[] = [
  { label: "Dashboard", route: "dashboard", to: "dashboard", icon: LayoutDashboard },
  { label: "Receivables", route: "receivables", to: "receivables", icon: List },
  { label: "Payment Reconciliation", route: "reconciliation/:tab", to: "reconciliation/review", icon: Scale },
  { label: "Conversations", route: "conversations", to: "conversations", icon: MessagesSquare },
  { label: "Disputes & Blockers", route: "cases", to: "cases", icon: ShieldAlert },
  { label: "Follow-ups", route: "followups", to: "followups", icon: Send },
  { label: "Review Inbox", route: "inbox", to: "inbox", icon: Inbox },
  { label: "Integrations", route: "integrations", to: "integrations", icon: Plug },
  { label: "Payment Accounts", route: "accounts", to: "accounts", icon: Landmark },
  { label: "Audit History", route: "audit", to: "audit", icon: History },
  { label: "Settings", route: "settings/:tab", to: "settings/business", icon: Settings },
];
