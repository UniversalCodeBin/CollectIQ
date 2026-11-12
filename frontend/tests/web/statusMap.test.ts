import { existsSync, readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import { allStatuses, statusOf } from "../../src/lib/statusMap";

const FORBIDDEN = /%|\bG-?\d{1,2}\b|\bgate\b|confidence|immutable|tamper|percent/i;

describe("status map", () => {
  it("status map has no percent or gate ID", () => {
    const entries = allStatuses();
    expect(entries.length).toBeGreaterThan(10);
    for (const { label } of entries) expect(label).not.toMatch(FORBIDDEN);
  });

  it("covers every payment status in the contract", () => {
    const contractPath = resolve(__dirname, "../../../CollectIQ_API_Contracts.yaml");
    if (!existsSync(contractPath)) {
      return;
    }
    const contract = readFileSync(contractPath, "utf-8");
    const block = /PaymentStatus:\s+type: string[\s\S]*?enum:\s+((?:\s*- \w+\s+)+)/.exec(contract)?.[1] ?? "";
    const values = [...block.matchAll(/- (\w+)/g)].map((match) => match[1] as string);
    expect(values).toContain("PAID_VERIFIED");
    for (const value of values) expect(statusOf("payment", value).known).toBe(true);
  });

  it("never says paid without verified", () => {
    for (const { kind, label } of allStatuses()) {
      if (kind === "payment" && /\bpaid\b/i.test(label) && !/partially/i.test(label)) expect(label).toMatch(/verified/i);
    }
  });

  it("gives every status an icon and a shape, so colour never carries the meaning alone", () => {
    for (const { icon, shape, tone } of allStatuses()) {
      expect(icon).toBeTruthy();
      expect(shape).toBeTruthy();
      expect(tone).toBeTruthy();
    }
  });

  it("uses a different shape for each of the dimensions", () => {
    const shapes = ["invoice", "payment", "dispute", "reminder", "evidence"].map(
      (kind) => allStatuses().find((entry) => entry.kind === kind)?.shape,
    );
    expect(new Set(shapes).size).toBe(5);
  });

  it("an unmapped value reads as unavailable and never shows the raw value", () => {
    const status = statusOf("payment", "SOME_NEW_VALUE");
    expect(status.known).toBe(false);
    expect(status.label).toBe("Status unavailable");
  });
});
