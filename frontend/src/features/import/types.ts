import type { components } from "../../lib/api-types";

export type ImportBatch = components["schemas"]["ImportBatchOut"];
export type ClientMatch = components["schemas"]["ImportClientMatchOut"];
export type RowDecision = components["schemas"]["ImportRowDecisionInRequest"];
export type ClientDecision = components["schemas"]["ImportClientDecisionInRequest"];
export type CommitDecisions = components["schemas"]["ImportDecisionsInRequest"];

export type FieldDiff = { field: string; current: unknown; incoming: unknown; kept: boolean };
export type LedgerMatch = { invoice_id: string; invoice_number: string; issue_date: string | null; gross_minor: number; currency: string };
export type TotalConflict = { total_minor: number; sum_minor: number };

/** The rows that need a person's attention. The server sends diffs, matches and conflict loosely typed. */
export type ReviewRow = Omit<components["schemas"]["ImportRowOut"], "diffs" | "matches" | "conflict"> & {
  diffs: FieldDiff[];
  matches: LedgerMatch[];
  conflict: TotalConflict | null;
};

export type Decisions = {
  skipInvalid: boolean;
  rows: Record<number, RowDecision>;
  clients: Record<string, ClientDecision>;
};

export const NO_DECISIONS: Decisions = { skipInvalid: false, rows: {}, clients: {} };
