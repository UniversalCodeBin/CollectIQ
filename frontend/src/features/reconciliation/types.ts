import type { ResponseOf } from "../../lib/api";

export type Proposal = {
  id: string;
  label: "Strong" | "Possible" | "Weak";
  ambiguous: boolean;
  reasons: { code: string; text: string }[];
  transaction: {
    id: string;
    amount_minor: number;
    currency: string;
    value_date: string;
    payer_descriptor: string | null;
    reference: string | null;
  };
  invoice: { id: string; invoice_number: string; client_name: string; outstanding_minor: number; due_date: string };
};

export type Payment = ResponseOf<{ method: "get"; path: "/api/v1/workspaces/{ws}/payments" }>["items"][number];
export type Unmatched = ResponseOf<{
  method: "get";
  path: "/api/v1/workspaces/{ws}/transactions/unmatched";
}>["items"][number];
