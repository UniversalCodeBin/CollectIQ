import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";
import { FactFrame } from "../../src/components/domain/FactFrame";
import { StatusChip } from "../../src/components/domain/StatusChip";
import { DataTable } from "../../src/components/ui/DataTable";
import { Dialog } from "../../src/components/ui/Dialog";
import { DisabledWithReason } from "../../src/components/ui/DisabledWithReason";
import { Drawer } from "../../src/components/ui/Drawer";
import { EmptyState } from "../../src/components/ui/EmptyState";
import { OfflineBanner } from "../../src/components/ui/OfflineBanner";
import { SampleDataBanner } from "../../src/components/ui/SampleDataBanner";

const COLUMNS = [
  { key: "number", header: "Invoice", rowHeader: true },
  { key: "amount", header: "Amount", numeric: true },
];

describe("StatusChip", () => {
  it("shows the plain label, an icon and the shape of its dimension", () => {
    render(<StatusChip kind="payment" value="PAID_VERIFIED" qualifier="evidence current to 28 Oct" />);
    const chip = screen.getByText(/Paid — verified/).closest("[data-shape]");
    expect(chip).toHaveAttribute("data-shape", "round");
    expect(chip).toHaveTextContent("evidence current to 28 Oct");
    expect(chip?.querySelector("svg")).not.toBeNull();
    expect(chip).not.toHaveTextContent("PAID_VERIFIED");
  });
});

describe("FactFrame", () => {
  it("frames each layer with its own style and a heading", () => {
    render(
      <>
        <FactFrame layer="original">quote</FactFrame>
        <FactFrame layer="ai">guess</FactFrame>
        <FactFrame layer="recorded" actor="Priya" source="Bank import row 14" timestamp="3 Nov">
          fact
        </FactFrame>
      </>,
    );
    const frame = (name: RegExp) => screen.getByRole("region", { name });
    expect(frame(/customer wrote/i)).toHaveAttribute("data-border", "solid");
    expect(frame(/ai interpretation \(unverified\)/i)).toHaveAttribute("data-border", "dashed");
    expect(frame(/recorded/i)).toHaveAttribute("data-border", "solid");
    expect(frame(/recorded/i)).toHaveTextContent("Bank import row 14");
    expect(frame(/recorded/i)).toHaveTextContent("Priya");
  });

  it("labels simulated AI output as such", () => {
    render(
      <FactFrame layer="ai" simulated>
        guess
      </FactFrame>,
    );
    expect(screen.getByRole("region", { name: /ai/i })).toHaveTextContent(/simulated/i);
  });

  it("the stylesheet draws AI dashed and the others solid", () => {
    const css = readFileSync(resolve(__dirname, "../../src/components/domain/FactFrame.module.css"), "utf-8");
    expect(css).toMatch(/\[data-border="dashed"\][^}]*dashed/);
    expect(css).toMatch(/\[data-border="solid"\][^}]*solid/);
  });
});

describe("DisabledWithReason", () => {
  it("stays focusable, states why, and does nothing when pressed", async () => {
    const onClick = vi.fn();
    render(<DisabledWithReason action={{ allowed: false, reason: "A dispute is open." }} onClick={onClick} label="Approve" />);
    const button = screen.getByRole("button", { name: "Approve" });
    expect(button).toHaveAttribute("aria-disabled", "true");
    expect(button).toHaveAccessibleDescription("A dispute is open.");
    expect(screen.getByText("A dispute is open.")).toBeVisible();
    await userEvent.tab();
    expect(button).toHaveFocus();
    await userEvent.click(button);
    expect(onClick).not.toHaveBeenCalled();
  });

  it("acts when the server allows it", async () => {
    const onClick = vi.fn();
    render(<DisabledWithReason action={{ allowed: true, reason: null }} onClick={onClick} label="Approve" />);
    const button = screen.getByRole("button", { name: "Approve" });
    expect(button).not.toHaveAttribute("aria-disabled", "true");
    await userEvent.click(button);
    expect(onClick).toHaveBeenCalledOnce();
  });
});

describe("DataTable", () => {
  it("renders headers, row headers and a label on each cell for card mode", () => {
    render(
      <DataTable
        caption="Invoices"
        columns={COLUMNS}
        rows={[{ id: "1", number: "INV-1", amount: "INR 100.00" }]}
        rowKey={(row) => row.id}
      />,
    );
    expect(screen.getByRole("table", { name: "Invoices" })).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "Amount" })).toBeInTheDocument();
    expect(screen.getByRole("rowheader", { name: /INV-1/ })).toBeInTheDocument();
    expect(screen.getByRole("cell", { name: /INR 100.00/ })).toHaveAttribute("data-label", "Amount");
  });

  it("shows the empty state in place of an empty table", () => {
    render(
      <DataTable
        caption="Invoices"
        columns={COLUMNS}
        rows={[]}
        rowKey={() => "x"}
        empty={<EmptyState title="No invoices yet" body="Import a file to begin." />}
      />,
    );
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
    expect(screen.getByText("No invoices yet")).toBeInTheDocument();
  });

  it("the stylesheet switches to cards by container width", () => {
    const css = readFileSync(resolve(__dirname, "../../src/components/ui/DataTable.module.css"), "utf-8");
    expect(css).toMatch(/container-type:\s*inline-size/);
    expect(css).toMatch(/@container[^{]*max-width/);
  });
});

describe("DataTable sorting", () => {
  it("exposes aria-sort and asks for the next order", async () => {
    const onSort = vi.fn();
    render(
      <DataTable
        caption="Invoices"
        columns={[{ key: "number", header: "Invoice", rowHeader: true, sortable: true }, COLUMNS[1] as { key: string; header: string }]}
        rows={[{ id: "1", number: "INV-1", amount: "1" }]}
        rowKey={(row) => row.id}
        sort={{ key: "number", direction: "ascending" }}
        onSort={onSort}
      />,
    );
    expect(screen.getByRole("columnheader", { name: "Invoice" })).toHaveAttribute("aria-sort", "ascending");
    await userEvent.click(screen.getByRole("button", { name: "Invoice" }));
    expect(onSort).toHaveBeenCalledWith("number");
  });
});

describe("destructive Dialog", () => {
  it("is an alertdialog and starts focus on Cancel", () => {
    render(
      <Dialog open onClose={() => {}} title="Remove member" destructive>
        <button>Remove</button>
        <button data-cancel>Cancel</button>
      </Dialog>,
    );
    expect(screen.getByRole("alertdialog", { name: "Remove member" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Cancel" })).toHaveFocus();
  });
});

for (const [name, Modal] of [
  ["Dialog", Dialog],
  ["Drawer", Drawer],
] as const) {
  describe(name, () => {
    function Host() {
      const [open, setOpen] = useState(false);
      return (
        <>
          <button onClick={() => setOpen(true)}>Open</button>
          <Modal open={open} onClose={() => setOpen(false)} title="Confirm">
            <button>First</button>
            <button>Last</button>
          </Modal>
        </>
      );
    }

    it("is a labelled modal, keeps focus inside and restores it on Escape", async () => {
      render(<Host />);
      const opener = screen.getByRole("button", { name: "Open" });
      await userEvent.click(opener);
      expect(screen.getByRole("dialog", { name: "Confirm" })).toHaveAttribute("aria-modal", "true");
      const last = screen.getByRole("button", { name: "Last" });
      last.focus();
      await userEvent.tab();
      expect(screen.getByRole("button", { name: "Close" })).toHaveFocus();
      await userEvent.tab({ shift: true });
      expect(last).toHaveFocus();
      await userEvent.keyboard("{Escape}");
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
      expect(opener).toHaveFocus();
    });
  });
}

describe("banners", () => {
  it("OfflineBanner follows the connection", () => {
    // A browser updates navigator.onLine before firing the event; jsdom does neither on its own.
    const onLine = vi.spyOn(window.navigator, "onLine", "get").mockReturnValue(true);
    render(<OfflineBanner />);
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
    onLine.mockReturnValue(false);
    act(() => void window.dispatchEvent(new Event("offline")));
    expect(screen.getByRole("status")).toHaveTextContent(/offline|connection/i);
    onLine.mockReturnValue(true);
    act(() => void window.dispatchEvent(new Event("online")));
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });

  it("SampleDataBanner cannot be dismissed", () => {
    render(<SampleDataBanner />);
    expect(screen.getByRole("status")).toHaveTextContent("Sample data");
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });
});
