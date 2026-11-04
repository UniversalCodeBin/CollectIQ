import { type FormEvent, useState } from "react";
import { Link, useLocation, useSearchParams } from "react-router";
import { Button } from "../../components/ui/Button";
import { fieldError, TextField } from "../../components/ui/Field";
import { MutationFeedback } from "../../components/ui/MutationFeedback";
import { useApiMutation } from "../../lib/api";
import { AuthPage, authStyles } from "./AuthPage";

function SendAgain({ initialEmail }: { initialEmail: string }) {
  const [email, setEmail] = useState(initialEmail);
  const resend = useApiMutation({ method: "post", path: "/api/v1/auth/verify-email/resend" });

  function submit(event: FormEvent) {
    event.preventDefault();
    resend.submit({ body: { email } });
  }

  return (
    <form className={authStyles.form} onSubmit={submit}>
      <TextField
        label="Email"
        type="email"
        name="email"
        autoComplete="username"
        required
        value={email}
        onChange={(event) => setEmail(event.target.value)}
        error={fieldError(resend.problem, "email")}
      />
      <MutationFeedback mutation={resend} />
      {resend.status === "success" && (
        <p role="status" className={authStyles.note}>
          If this address needs confirming, we've sent another email. It can take a few minutes.
        </p>
      )}
      <Button type="submit" disabled={resend.status === "pending"}>
        Send it again
      </Button>
    </form>
  );
}

function Confirm({ token, email }: { token: string; email: string }) {
  const verify = useApiMutation({ method: "post", path: "/api/v1/auth/verify-email" });

  if (verify.status === "success") {
    return (
      <AuthPage title="Email confirmed">
        <p className={authStyles.note}>Your email address is confirmed. Sign in to set up your workspace.</p>
        <Link to="/login">Sign in</Link>
      </AuthPage>
    );
  }
  return (
    <AuthPage title="Confirm your email">
      <p className={authStyles.note}>Press the button to confirm this email address belongs to you.</p>
      <MutationFeedback mutation={verify} />
      {verify.status === "problem" ? (
        <SendAgain initialEmail={email} />
      ) : (
        <Button
          variant="primary"
          disabled={verify.status === "pending"}
          onClick={() => verify.submit({ body: { token } })}
        >
          Confirm my email
        </Button>
      )}
    </AuthPage>
  );
}

export function VerifyEmailPage() {
  const [params] = useSearchParams();
  const { state } = useLocation();
  const token = params.get("token");
  const email = (state as { email?: string } | null)?.email ?? "";

  if (token) return <Confirm token={token} email={email} />;
  return (
    <AuthPage title="Check your email">
      <p className={authStyles.note}>We sent a link to confirm your address. Open it to continue.</p>
      <SendAgain initialEmail={email} />
      <Link to="/login">Back to sign in</Link>
    </AuthPage>
  );
}
