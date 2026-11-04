import { type ApiProblem, plainProblem } from "../../lib/api";
import styles from "./Feedback.module.css";

export function ProblemMessage({ problem }: { problem: ApiProblem }) {
  const { message, fields, correlationId } = plainProblem(problem);
  return (
    <div role="alert" className={styles.problem}>
      <p>{message}</p>
      {fields.length > 0 && (
        <ul className={styles.fields}>
          {fields.map((field, index) => (
            <li key={`${field.field ?? "form"}-${index}`}>{field.message}</li>
          ))}
        </ul>
      )}
      {correlationId && <p className={styles.reference}>Reference: {correlationId}</p>}
    </div>
  );
}
