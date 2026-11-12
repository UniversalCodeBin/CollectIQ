import { CircleCheck, Mail, MailOpen } from "lucide-react";
import { type FormEvent, useState } from "react";
import { Link, useLocation, useSearchParams } from "react-router";
import { Button } from "../../components/ui/Button";
import { fieldError, TextField } from "../../components/ui/Field";
import { MutationFeedback } from "../../components/ui/MutationFeedback";
import { useApiMutation } from "../../lib/api";
import { AuthPage, authStyles } from "./AuthPage";
import { checkEmail, clearError, type FieldErrors, focusFirstError } from "./validation";

function SendAgain({ initialEmail }: { initialEmail: string }) {
  const [email, setEmail] = useState(initialEmail);
  const [errors, setErrors] = useState<FieldErrors>({});
  const resend = useApiMutation({ method: "post", path: "/api/v1/auth/verify-email/resend" });
  const pending = resend.status === "pending";

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (pending) return;
    const found: FieldErrors = { email: checkEmail(email) };
    setErrors(found);
    if (found.email) return focusFirstError(event.currentTarget, found);
    resend.submit({ body: { email } });
  }

  return (
    <form className={authStyles.form} onSubmit={submit} noValidate>
      <TextField
        label="Email"
        type="email"
        name="email"
        icon={Mail}
        autoComplete="username"
        inputMode="email"
        required
        hint="Didn't get it? Check spam, or send it again."
        value={email}
        onChange={(event) => {
          setEmail(event.target.value);
          setErrors(clearError("email"));
        }}
        error={errors.email ?? fieldError(resend.problem, "email")}
      />
      <MutationFeedback mutation={resend} />
      {resend.status === "success" && (
        <p role="status" className={authStyles.note}>
          If this address needs confirming, we've sent another email. It can take a few minutes.
        </p>
      )}
      <Button type="submit" block busy={pending} disabled={pending}>
        Send it again
      </Button>
    </form>
  );
}

function Confirm({ token, email }: { token: string; email: string }) {
  const verify = useApiMutation({ method: "post", path: "/api/v1/auth/verify-email" });
  const pending = verify.status === "pending";

  if (verify.status === "success") {
    return (
      <AuthPage title="Email confirmed">
        <div className={authStyles.outcome}>
          <CircleCheck size={20} aria-hidden="true" />
          <p>Your email address is confirmed. Sign in to set up your workspace.</p>
        </div>
        <Link className={authStyles.back} to="/login">
          Sign in
        </Link>
      </AuthPage>
    );
  }
  return (
    <AuthPage title="Confirm your email" lead="Press the button to confirm this email address belongs to you.">
      <MutationFeedback mutation={verify} />
      {verify.status === "problem" ? (
        <SendAgain initialEmail={email} />
      ) : (
        <Button
          variant="primary"
          size="lg"
          block
          busy={pending}
          disabled={pending}
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
      <div className={authStyles.outcome}>
        <MailOpen size={20} aria-hidden="true" />
        <p>We sent a link to confirm your address. Open it to continue. The link works once.</p>
      </div>
      <SendAgain initialEmail={email} />
      <Link className={authStyles.back} to="/login">
        Back to sign in
      </Link>
    </AuthPage>
  );
}
