import axe from "axe-core";
import { render } from "@testing-library/react";
import type { ReactElement } from "react";
import { act } from "react";
import { describe, expect, it, vi } from "vitest";
import { FactFrame } from "../../src/components/domain/FactFrame";
import { StatusChip } from "../../src/components/domain/StatusChip";
import { Button } from "../../src/components/ui/Button";
import { DataTable } from "../../src/components/ui/DataTable";
import { Dialog } from "../../src/components/ui/Dialog";
import { DisabledWithReason } from "../../src/components/ui/DisabledWithReason";
import { Drawer } from "../../src/components/ui/Drawer";
import { EmptyState } from "../../src/components/ui/EmptyState";
import { OfflineBanner } from "../../src/components/ui/OfflineBanner";
import { ProblemMessage } from "../../src/components/ui/ProblemMessage";
import { SampleDataBanner } from "../../src/components/ui/SampleDataBanner";
import { ApiProblem } from "../../src/lib/api";

const problem = new ApiProblem({
  status: 422,
  code: "VALIDATION_FAILED",
  detail: "Check the highlighted fields.",
  correlationId: "corr-1",
  errors: [{ field: "email", message: "Enter a valid email address." }],
});

const CASES: Array<[string, ReactElement]> = [
  ["Button", <Button key="b">Save</Button>],
  ["StatusChip", <StatusChip key="s" kind="dispute" value="OPEN" />],
  [
    "FactFrame",
    <div key="f">
      <FactFrame layer="original">quote</FactFrame>
      <FactFrame layer="ai">guess</FactFrame>
      <FactFrame layer="recorded">fact</FactFrame>
    </div>,
  ],
  ["ProblemMessage", <ProblemMessage key="p" problem={problem} />],
  ["DisabledWithReason", <DisabledWithReason key="d" action={{ allowed: false, reason: "Why." }} label="Go" onClick={() => {}} />],
  [
    "DataTable",
    <DataTable
      key="t"
      caption="Invoices"
      columns={[
        { key: "n", header: "Invoice", rowHeader: true },
        { key: "a", header: "Amount", numeric: true },
      ]}
      rows={[{ id: "1", n: "INV-1", a: "INR 1.00" }]}
      rowKey={(row) => row.id}
    />,
  ],
  [
    "Dialog",
    <Dialog key="g" open onClose={() => {}} title="Confirm">
      <button>OK</button>
    </Dialog>,
  ],
  [
    "Drawer",
    <Drawer key="w" open onClose={() => {}} title="Details">
      <button>OK</button>
    </Drawer>,
  ],
  ["EmptyState", <EmptyState key="e" title="Nothing yet" body="Add one." />],
  ["OfflineBanner", <OfflineBanner key="o" />],
  ["SampleDataBanner", <SampleDataBanner key="m" />],
];

describe("accessibility", () => {
  it.each(CASES)("axe finds nothing on %s", async (_name, element) => {
    vi.spyOn(window.navigator, "onLine", "get").mockReturnValue(false);
    render(element);
    let results: axe.AxeResults | undefined;
    await act(async () => {
      // jsdom has no layout, so contrast is proven from the tokens, not here.
      results = await axe.run(document.body, {
        rules: { "color-contrast": { enabled: false }, region: { enabled: false } },
      });
    });
    expect(results?.violations.map((violation) => violation.id)).toEqual([]);
  });
});
