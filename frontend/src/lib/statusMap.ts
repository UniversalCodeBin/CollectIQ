import {
  Archive,
  Ban,
  Bell,
  CalendarCheck,
  CalendarClock,
  Check,
  Circle,
  CircleDashed,
  CircleDot,
  CircleHelp,
  CirclePause,
  Clock,
  Flag,
  Hourglass,
  type LucideIcon,
  PenLine,
  Send,
  ShieldCheck,
  TriangleAlert,
  Unplug,
  UserCheck,
  X,
} from "lucide-react";

export type StatusTone =
  | "verified"
  | "neutral"
  | "partial"
  | "awaiting"
  | "uncertain"
  | "disputed"
  | "commitment"
  | "scheduled"
  | "paused"
  | "review"
  | "error";

export type StatusShape = "outline" | "round" | "flag" | "pill" | "ring" | "tag";

export type StatusKind =
  | "payment"
  | "invoice"
  | "dispute"
  | "reminder"
  | "commitment"
  | "review"
  | "integration"
  | "evidence"
  | "match";

type Entry = { label: string; icon: LucideIcon; tone: StatusTone };

const SHAPES: Record<StatusKind, StatusShape> = {
  payment: "round",
  invoice: "outline",
  dispute: "flag",
  reminder: "pill",
  commitment: "pill",
  review: "tag",
  integration: "tag",
  evidence: "ring",
  match: "tag",
};

const STATUS_MAP: Record<StatusKind, Record<string, Entry>> = {
  payment: {
    OUTSTANDING: { label: "Outstanding", icon: Circle, tone: "neutral" },
    PARTIALLY_PAID: { label: "Partially paid", icon: CircleDot, tone: "partial" },
    AWAITING_VERIFICATION: { label: "Awaiting verification", icon: Hourglass, tone: "awaiting" },
    UNCERTAIN: { label: "Payment uncertain", icon: CircleHelp, tone: "uncertain" },
    PAID_VERIFIED: { label: "Paid — verified", icon: ShieldCheck, tone: "verified" },
  },
  invoice: {
    OPEN: { label: "Open", icon: Circle, tone: "neutral" },
    CANCELLED: { label: "Cancelled", icon: Ban, tone: "neutral" },
    VOID: { label: "Void", icon: Ban, tone: "neutral" },
    ACTIVE: { label: "Active", icon: Circle, tone: "neutral" },
    PENDING_REVIEW: { label: "Waiting for your review", icon: UserCheck, tone: "review" },
    WRITTEN_OFF: { label: "Written off", icon: X, tone: "neutral" },
    ARCHIVED: { label: "Archived", icon: Archive, tone: "neutral" },
  },
  dispute: {
    OPEN: { label: "Dispute open", icon: Flag, tone: "disputed" },
    IN_REVIEW: { label: "Dispute open — in review", icon: Flag, tone: "disputed" },
    AWAITING_CUSTOMER: { label: "Dispute open — awaiting customer", icon: Flag, tone: "disputed" },
    RESOLVED: { label: "Dispute resolved", icon: Check, tone: "neutral" },
  },
  reminder: {
    DRAFT: { label: "Draft", icon: PenLine, tone: "neutral" },
    APPROVED: { label: "Approved — ready to send", icon: Bell, tone: "scheduled" },
    SCHEDULED: { label: "Approved — ready to send", icon: Bell, tone: "scheduled" },
    SENDING: { label: "Sending", icon: Send, tone: "scheduled" },
    SUBMITTED: { label: "Submitted", icon: Send, tone: "scheduled" },
    MARKED_SENT: { label: "Marked as sent", icon: Check, tone: "neutral" },
    SUBMISSION_UNKNOWN: { label: "Might have been sent", icon: CircleHelp, tone: "uncertain" },
    FAILED: { label: "Failed", icon: TriangleAlert, tone: "error" },
    EXPIRED: { label: "Expired", icon: Clock, tone: "neutral" },
    INVALIDATED: { label: "Invalidated", icon: Ban, tone: "neutral" },
    SUPPRESSED: { label: "Reminders paused", icon: CirclePause, tone: "paused" },
    SNOOZED: { label: "Reminders paused", icon: CirclePause, tone: "paused" },
    NOT_CONTACTED: { label: "Not contacted yet", icon: Circle, tone: "neutral" },
    DRAFT_READY: { label: "Draft ready for your review", icon: PenLine, tone: "review" },
    WAITING_FOR_CUSTOMER: { label: "Waiting for the customer", icon: Clock, tone: "neutral" },
    NEEDS_REVIEW: { label: "Needs your review", icon: UserCheck, tone: "review" },
    RESOLVED: { label: "Resolved", icon: Check, tone: "neutral" },
  },
  commitment: {
    CONFIRMED: { label: "Stated date", icon: CalendarCheck, tone: "commitment" },
    INDICATED: { label: "Indicated timing", icon: CalendarClock, tone: "commitment" },
  },
  review: {
    NEEDS_REVIEW: { label: "Needs your review", icon: UserCheck, tone: "review" },
  },
  integration: {
    NEEDS_REAUTH: { label: "Needs reauthorization", icon: Unplug, tone: "error" },
    DEGRADED_MONITORING: { label: "Reply monitoring delayed", icon: Unplug, tone: "error" },
  },
  evidence: {
    CURRENT: { label: "Current", icon: Circle, tone: "verified" },
    NOT_CURRENT: { label: "Not current", icon: CircleDot, tone: "uncertain" },
    MISSING: { label: "Missing", icon: CircleDashed, tone: "neutral" },
    SUPPORTED: { label: "Current", icon: Circle, tone: "verified" },
    STALE: { label: "Not current", icon: CircleDot, tone: "uncertain" },
  },
  match: {
    PROPOSED: { label: "Suggested — not applied", icon: CircleHelp, tone: "awaiting" },
    CONFIRMED: { label: "Applied", icon: Check, tone: "verified" },
    REJECTED: { label: "Not a match", icon: X, tone: "neutral" },
    SUPERSEDED: { label: "Replaced by a newer suggestion", icon: Clock, tone: "neutral" },
  },
};

export type ResolvedStatus = Entry & { known: boolean; shape: StatusShape };

/** An unmapped value never reaches the screen raw. */
export function statusOf(kind: StatusKind, value: string): ResolvedStatus {
  const entry = Object.hasOwn(STATUS_MAP[kind], value) ? STATUS_MAP[kind][value] : undefined;
  if (entry) return { ...entry, known: true, shape: SHAPES[kind] };
  return { label: "Status unavailable", icon: CircleHelp, tone: "neutral", known: false, shape: SHAPES[kind] };
}

export function allStatuses(): Array<ResolvedStatus & { kind: StatusKind; value: string }> {
  return (Object.keys(STATUS_MAP) as StatusKind[]).flatMap((kind) =>
    Object.keys(STATUS_MAP[kind]).map((value) => ({ ...statusOf(kind, value), kind, value })),
  );
}
