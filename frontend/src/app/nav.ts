import { Landmark, LayoutDashboard, Scale, Settings, type LucideIcon } from "lucide-react";

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
  { label: "Payment Reconciliation", route: "reconciliation/:tab", to: "reconciliation/review", icon: Scale },
  { label: "Payment Accounts", route: "accounts", to: "accounts", icon: Landmark },
  { label: "Settings", route: "settings/:tab", to: "settings/automation", icon: Settings },
];
