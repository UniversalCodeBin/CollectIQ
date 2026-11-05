import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router";
import { ProblemMessage } from "../../components/ui/ProblemMessage";
import { ApiProblem, apiRequest } from "../../lib/api";
import { DoneStep } from "./DoneStep";
import styles from "./ImportPage.module.css";
import { MappingStep } from "./MappingStep";
import { ReviewStep } from "./ReviewStep";
import type { ImportBatch } from "./types";
import { UploadStep } from "./UploadStep";

const key = (workspace: string, id: string) => ["import", workspace, id] as const;

/** Where you are comes from the server's record of the import, so a reload or a shared link lands in the same place. */
export function ImportPage() {
  const { ws = "" } = useParams();
  const [params, setParams] = useSearchParams();
  const id = params.get("batch");
  const client = useQueryClient();
  const [editingColumns, setEditingColumns] = useState(false);

  const found = useQuery({
    queryKey: key(ws, id ?? ""),
    enabled: Boolean(id),
    queryFn: () => apiRequest({ method: "get", path: "/api/v1/workspaces/{ws}/imports/{import_id}" }, { path: { ws, import_id: id ?? "" } }),
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

  let body;
  if (!id) {
    body = <UploadStep workspace={ws} onUploaded={adopt} />;
  } else if (found.isPending) {
    body = <p role="status">Loading your import…</p>;
  } else if (found.isError || !found.data) {
    const problem = found.error instanceof ApiProblem ? found.error : new ApiProblem({ status: 0, code: "NETWORK", detail: "", correlationId: null });
    body = (
      <div className={styles.stack}>
        <ProblemMessage problem={problem} />
        <Link to={`/w/${ws}/import/invoices`}>Start a new import</Link>
      </div>
    );
  } else if (found.data.status === "COMMITTED") {
    body = <DoneStep batch={found.data} workspace={ws} onAnother={startOver} />;
  } else if (found.data.status === "DISCARDED") {
    body = (
      <section className={styles.card}>
        <p>This import was discarded.</p>
        <Link to={`/w/${ws}/import/invoices`}>Start a new import</Link>
      </section>
    );
  } else if (!found.data.mapping || editingColumns) {
    body = <MappingStep workspace={ws} batch={found.data} onMapped={adopt} />;
  } else {
    body = <ReviewStep workspace={ws} batch={found.data} onChanged={adopt} onDiscarded={startOver} onChangeColumns={() => setEditingColumns(true)} />;
  }

  return (
    <div className={styles.page}>
      <h1 className={styles.title}>Import invoices</h1>
      {body}
    </div>
  );
}
