import { CircleCheck, Link2Off, Lock, Mail, MailCheck } from "lucide-react";
import { type FormEvent, useState } from "react";
import { Link, useSearchParams } from "react-router";
import { Button } from "../../components/ui/Button";
import { fieldError, PasswordField, TextField } from "../../components/ui/Field";
import { MutationFeedback } from "../../components/ui/MutationFeedback";
import { useApiMutation } from "../../lib/api";
import { AuthPage, authStyles } from "./AuthPage";
import {
  checkEmail,
  checkNewPassword,
  clearError,
  type FieldErrors,
  focusFirstError,
  PasswordRules,
} from "./validation";

export function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [errors, setErrors] = useState<FieldErrors>({});
  const request = useApiMutation({ method: "post", path: "/api/v1/auth/password-reset/request" });
  const pending = request.status === "pending";

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (pending) return;
    const found: FieldErrors = { email: checkEmail(email) };
    setErrors(found);
    if (found.email) return focusFirstError(event.currentTarget, found);
    request.submit({ body: { email } });
  }

  return (
    <AuthPage title="Reset your password" lead="Enter the email you sign in with and we'll send you a reset link.">
      {request.status === "success" ? (
        // Same words whether or not the address has an account, so this page can't be used to test addresses.
        <div role="status" className={authStyles.outcome}>
          <MailCheck size={20} aria-hidden="true" />
          <p>If an account exists for this address, we've emailed a link to choose a new password.</p>
        </div>
      ) : (
        <form className={authStyles.form} onSubmit={submit} noValidate>
          <TextField
            label="Email"
            type="email"
            name="email"
            icon={Mail}
            autoComplete="username"
            inputMode="email"
            required
            value={email}
            onChange={(event) => {
              setEmail(event.target.value);
              setErrors(clearError("email"));
            }}
            error={errors.email ?? fieldError(request.problem, "email")}
          />
          <MutationFeedback mutation={request} />
          <Button type="submit" variant="primary" size="lg" block busy={pending} disabled={pending}>
            Send reset link
          </Button>
        </form>
      )}
      <Link className={authStyles.back} to="/login">
        Back to sign in
      </Link>
    </AuthPage>
  );
}

export function ResetPasswordPage() {
  const [params] = useSearchParams();
  const [password, setPassword] = useState("");
  const [errors, setErrors] = useState<FieldErrors>({});
  const confirm = useApiMutation({ method: "post", path: "/api/v1/auth/password-reset/confirm" });
  const token = params.get("token");
  const pending = confirm.status === "pending";

  if (!token) {
    return (
      <AuthPage title="This link is incomplete">
        <div className={authStyles.outcome}>
          <Link2Off size={20} aria-hidden="true" />
          <p>Open the full link from the email, or ask for a new one.</p>
        </div>
        <Link className={authStyles.back} to="/forgot-password">
          Request a new link
        </Link>
      </AuthPage>
    );
  }
  if (confirm.status === "success") {
    return (
      <AuthPage title="Password changed">
        <div className={authStyles.outcome}>
          <CircleCheck size={20} aria-hidden="true" />
          <p>Your password has been changed. Use the new one to sign in.</p>
        </div>
        <Link className={authStyles.back} to="/login">
          Sign in
        </Link>
      </AuthPage>
    );
  }

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (pending) return;
    const found: FieldErrors = { new_password: checkNewPassword(password) };
    setErrors(found);
    if (found.new_password) return focusFirstError(event.currentTarget, found);
    confirm.submit({ body: { token: token as string, new_password: password } });
  }

  return (
    <AuthPage title="Choose a new password" lead="Pick something you haven't used here before.">
      <form className={authStyles.form} onSubmit={submit} noValidate>
        <PasswordField
          label="New password"
          name="new_password"
          icon={Lock}
          autoComplete="new-password"
          required
          minLength={12}
          maxLength={128}
          hint="Use at least 12 characters. A few unrelated words work well."
          value={password}
          onChange={(event) => {
            setPassword(event.target.value);
            setErrors(clearError("new_password"));
          }}
          error={errors.new_password ?? fieldError(confirm.problem, "new_password")}
        />
        <PasswordRules password={password} />
        <MutationFeedback mutation={confirm} />
        <Button type="submit" variant="primary" size="lg" block busy={pending} disabled={pending}>
          Set new password
        </Button>
      </form>
      <Link className={authStyles.back} to="/forgot-password">
        Request a new link
      </Link>
    </AuthPage>
  );
}
