// FILE GUIDE: CSV invoice import (SCR-05). Upload, match columns, review, done. Which step you are on comes from the
// server's record of the import, so a reload or a shared link lands in the same place. Nothing is added to the
// workspace until the person chooses Commit Invoices on the review step.
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router";
import { ButtonLink } from "../../components/ui/Button";
import { Callout } from "../../components/ui/Callout";
import { Page, PageHeader } from "../../components/ui/Page";
import { ProblemMessage } from "../../components/ui/ProblemMessage";
import { ApiProblem, apiRequest } from "../../lib/api";
import { DoneStep } from "./DoneStep";
import styles from "./ImportPage.module.css";
import { MappingStep } from "./MappingStep";
import { ReviewStep } from "./ReviewStep";
import type { ImportBatch } from "./types";
import { UploadStep } from "./UploadStep";

const key = (workspace: string, id: string) => ["import", workspace, id] as const;

const STEPS = ["Upload a file", "Match columns", "Review and import", "Done"] as const;

/** The four steps, with the current one announced. Shown only while the step is known. */
function Steps({ current }: { current: number }) {
  return (
    <ol className={styles.steps} aria-label="Import steps">
      {STEPS.map((label, index) => {
        const number = index + 1;
        const state = number < current ? "done" : number === current ? "current" : "todo";
        return (
          <li
            key={label}
            className={styles.step}
            data-state={state}
            aria-current={state === "current" ? "step" : undefined}
          >
            <span className={styles.stepNum} aria-hidden="true">
              {number}
            </span>
            <span>
              {label}
              {state === "done" && <span className="visually-hidden"> (done)</span>}
            </span>
          </li>
        );
      })}
    </ol>
  );
}

export function ImportPage() {
  const { ws = "" } = useParams();
  const [params, setParams] = useSearchParams();
  const id = params.get("batch");
  const client = useQueryClient();
  const [editingColumns, setEditingColumns] = useState(false);

  const found = useQuery({
    queryKey: key(ws, id ?? ""),
    enabled: Boolean(id),
    queryFn: () =>
      apiRequest(
        { method: "get", path: "/api/v1/workspaces/{ws}/imports/{import_id}" },
        { path: { ws, import_id: id ?? "" } },
      ),
  });

  const adopt = useCallback(
    (batch: ImportBatch) => {
      client.setQueryData(key(ws, batch.id), batch);
      setEditingColumns(false);
      setParams({ batch: batch.id }, { replace: true });
    },
    [client, ws, setParams],
  );

  const startOver = useCallback(() => {
    if (id) client.removeQueries({ queryKey: key(ws, id) });
    setEditingColumns(false);
    setParams({}, { replace: true });
  }, [client, id, ws, setParams]);

  const restart = <Link to={`/w/${ws}/import/invoices`}>Start a new import</Link>;
  let step = 0;
  let body;
  if (!id) {
    step = 1;
    body = <UploadStep workspace={ws} onUploaded={adopt} />;
  } else if (found.isPending) {
    body = (
      <p role="status" className={styles.hint}>
        Loading your import…
      </p>
    );
  } else if (found.isError || !found.data) {
    const problem =
      found.error instanceof ApiProblem
        ? found.error
        : new ApiProblem({ status: 0, code: "NETWORK", detail: "", correlationId: null });
    body = (
      <div className={styles.stack}>
        <ProblemMessage problem={problem} />
        {restart}
      </div>
    );
  } else if (found.data.status === "COMMITTED") {
    step = 4;
    body = <DoneStep batch={found.data} workspace={ws} onAnother={startOver} />;
  } else if (found.data.status === "DISCARDED") {
    body = (
      <Callout tone="info" title="This import was discarded">
        <p>Nothing from it was added to your invoices. {restart}</p>
      </Callout>
    );
  } else if (!found.data.mapping || editingColumns) {
    step = 2;
    body = <MappingStep workspace={ws} batch={found.data} onMapped={adopt} />;
  } else {
    step = 3;
    body = (
      <ReviewStep
        workspace={ws}
        batch={found.data}
        onChanged={adopt}
        onDiscarded={startOver}
        onChangeColumns={() => setEditingColumns(true)}
      />
    );
  }

  return (
    <Page width="narrow">
      <PageHeader
        title="Import invoices"
        description="Bring in invoices exported from your accounting tool as a CSV file. Your accounting tool stays the record; nothing is added here until you review the rows and confirm."
        actions={
          <ButtonLink to={`/w/${ws}/import/pdf`} variant="quiet">
            Read an invoice from a PDF instead
          </ButtonLink>
        }
      />
      {step > 0 && <Steps current={step} />}
      {body}
    </Page>
  );
}
