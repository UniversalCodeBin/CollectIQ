import type { ClientMatch, CommitDecisions, Decisions, ImportBatch, ReviewRow } from "./types";

function plural(count: number, one: string, many: string): string {
  return `${count} ${count === 1 ? one : many}`;
}

export function rowsOf(batch: ImportBatch): ReviewRow[] {
  return batch.rows as unknown as ReviewRow[];
}

export function invalidCount(batch: ImportBatch): number {
  return batch.counts.invalid ?? 0;
}

export function isDecided(row: ReviewRow, decisions: Decisions): boolean {
  const decision = decisions.rows[row.row];
  if (!decision) return false;
  return row.status === "CONFLICT"
    ? decision.action === "IGNORE" || decision.total_source !== undefined
    : decision.action !== undefined;
}

export function undecidedClients(batch: ImportBatch, decisions: Decisions): ClientMatch[] {
  return batch.client_matches.filter((match) => match.decision_required && !decisions.clients[match.name]);
}

/**
 * Why the file cannot be committed yet. The wording matches what the server says when it refuses,
 * but the server's own verdict always assumes no decisions, so the screen works this out itself.
 */
export function commitBlockers(batch: ImportBatch, decisions: Decisions): string[] {
  const rows = rowsOf(batch);
  const total = batch.counts.total_rows ?? 0;
  const invalid = invalidCount(batch);
  const reasons: string[] = [];
  if (total > 0 && invalid === total) {
    reasons.push("No row in this file can be imported yet. Check the problems listed for each row.");
  }
  const waiting = undecidedClients(batch, decisions).reduce((sum, match) => sum + match.rows, 0);
  if (waiting) reasons.push(`Choose which client ${plural(waiting, "row belongs", "rows belong")} to.`);
  const conflicts = rows.filter((row) => row.status === "CONFLICT" && !isDecided(row, decisions)).length;
  if (conflicts) reasons.push(`Choose the total to keep for ${plural(conflicts, "row", "rows")}.`);
  const matches = rows.filter(
    (row) => row.status !== "INVALID" && row.status !== "CONFLICT" && !isDecided(row, decisions),
  ).length;
  if (matches) {
    reasons.push(`Decide what to do with ${plural(matches, "row that matches", "rows that match")} an invoice.`);
  }
  if (invalid && invalid !== total && !decisions.skipInvalid) {
    reasons.push(`Fix ${plural(invalid, "invalid row", "invalid rows")} or choose to skip them.`);
  }
  return reasons;
}

/** Only what the person chose is sent, so an empty choice is never read as a decision. */
export function toCommitBody(decisions: Decisions): { decisions?: CommitDecisions } {
  const chosen: CommitDecisions = {};
  if (decisions.skipInvalid) chosen.skip_invalid = true;
  if (Object.keys(decisions.rows).length) {
    chosen.rows = Object.fromEntries(Object.entries(decisions.rows).map(([row, decision]) => [row, decision]));
  }
  if (Object.keys(decisions.clients).length) chosen.clients = decisions.clients;
  return Object.keys(chosen).length ? { decisions: chosen } : {};
}
