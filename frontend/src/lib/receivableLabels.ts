// Plain-language names for the dashboard tiles and aging buckets. The dashboard and the receivables filters
// both use them, so a figure keeps the same name when you follow it from one screen to the other.

const TILE_LABELS: Record<string, string> = {
  outstanding: "Outstanding",
  overdue: "Overdue",
  due_soon: "Due soon",
  partially_paid: "Partly paid",
  needs_verification: "Needs checking",
  disputed: "In dispute",
  snoozed: "Paused",
};

const BUCKET_LABELS: Record<string, string> = {
  not_due: "Not due yet",
  "1-30": "1-30 days late",
  "31-60": "31-60 days late",
  "61-90": "61-90 days late",
  "90+": "Over 90 days late",
  "91_plus": "Over 90 days late",
};

export const tileLabel = (key: string) => TILE_LABELS[key] ?? key.replace(/_/g, " ");

export const bucketLabel = (key: string) =>
  BUCKET_LABELS[key] ?? (/^\d/.test(key) ? `${key} days late` : key.replace(/_/g, " "));
