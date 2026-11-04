import type { ApiProblem, MutationStatus } from "../../lib/api";
import { Button } from "./Button";
import styles from "./Feedback.module.css";
import { ProblemMessage } from "./ProblemMessage";

type Props = {
  mutation: {
    status: MutationStatus;
    problem: ApiProblem | null;
    checking: boolean;
    checkStatus: () => void;
  };
};

/** Shows a refusal, or, when no answer arrived, offers Check status instead of a second submit. */
export function MutationFeedback({ mutation }: Props) {
  const { status, problem, checking, checkStatus } = mutation;
  if (status === "unknown") {
    const refused = problem && problem.status > 0 && problem.status < 500;
    return (
      <div className={styles.unknown}>
        <p role="status">
          We could not confirm whether this went through. Checking is safe: it can't do the action twice.
        </p>
        {refused && <ProblemMessage problem={problem} />}
        <Button variant="primary" aria-disabled={checking || undefined} onClick={checkStatus}>
          Check status
        </Button>
      </div>
    );
  }
  return status === "problem" && problem ? <ProblemMessage problem={problem} /> : null;
}
