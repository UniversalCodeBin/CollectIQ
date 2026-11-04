import type { LucideIcon } from "lucide-react";

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
export const NAV_ITEMS: NavItem[] = [];
