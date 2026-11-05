import { type FormEvent, useEffect, useRef, useState } from "react";
import { Button } from "../../components/ui/Button";
import { TextField } from "../../components/ui/Field";
import { MutationFeedback } from "../../components/ui/MutationFeedback";
import { ProblemMessage } from "../../components/ui/ProblemMessage";
import { ApiProblem, useApiMutation } from "../../lib/api";
import styles from "./ImportPage.module.css";
import type { ImportBatch } from "./types";

const isCsv = (file: File) => /\.csv$/i.test(file.name);

function localProblem(message: string): ApiProblem {
  return new ApiProblem({ status: 400, code: "VALIDATION_FAILED", detail: "", correlationId: null, errors: [{ field: "file", message }] });
}

export function UploadStep({ workspace, onUploaded }: { workspace: string; onUploaded: (batch: ImportBatch) => void }) {
  const upload = useApiMutation({ method: "post", path: "/api/v1/workspaces/{ws}/imports/invoices" }, { idempotent: true, secretBody: true });
  const [file, setFile] = useState<File | null>(null);
  const [refusal, setRefusal] = useState<ApiProblem | null>(null);
  const handed = useRef(false);
  const created = upload.status === "success" ? upload.data : undefined;

  useEffect(() => {
    if (created && !handed.current) {
      handed.current = true;
      onUploaded(created);
    }
  }, [created, onUploaded]);

  function submit(event: FormEvent) {
    event.preventDefault();
    if (!file) return setRefusal(localProblem("Choose a CSV file to upload."));
    if (!isCsv(file)) return setRefusal(localProblem("Choose a CSV file. Other kinds of file can't be imported."));
    setRefusal(null);
    const body = new FormData();
    body.set("file", file);
    upload.submit({ path: { ws: workspace }, body });
  }

  return (
    <form onSubmit={submit} className={styles.card} noValidate>
      <h2 className={styles.heading}>Upload your invoices</h2>
      <p className={styles.lead}>
        Export your invoices from your accounting tool as a CSV file and upload it here. Nothing is added until you review it and
        choose Commit Invoices.
      </p>
      <TextField
        label="Choose a CSV file"
        type="file"
        accept=".csv,text/csv"
        hint="One invoice per row, with a header row naming each column."
        onChange={(event) => {
          setFile(event.target.files?.[0] ?? null);
          setRefusal(null);
        }}
      />
      {refusal ? <ProblemMessage problem={refusal} /> : <MutationFeedback mutation={upload} />}
      <div>
        <Button variant="primary" type="submit" aria-disabled={upload.status === "pending" || undefined}>
          Upload file
        </Button>
      </div>
    </form>
  );
}
