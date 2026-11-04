import { type FormEvent, useState } from "react";
import { Link, useSearchParams } from "react-router";
import { Button } from "../../components/ui/Button";
import { fieldError, TextField } from "../../components/ui/Field";
import { MutationFeedback } from "../../components/ui/MutationFeedback";
import { useApiMutation } from "../../lib/api";
import { AuthPage, authStyles } from "./AuthPage";

export function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const request = useApiMutation({ method: "post", path: "/api/v1/auth/password-reset/request" });

  function submit(event: FormEvent) {
    event.preventDefault();
    request.submit({ body: { email } });
  }

  return (
    <AuthPage title="Reset your password">
      {request.status === "success" ? (
        <p role="status" className={authStyles.note}>
          If an account exists for this address, we've emailed a link to choose a new password.
        </p>
      ) : (
        <form className={authStyles.form} onSubmit={submit}>
          <TextField
            label="Email"
            type="email"
            name="email"
            autoComplete="username"
            required
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            error={fieldError(request.problem, "email")}
          />
          <MutationFeedback mutation={request} />
          <Button type="submit" variant="primary" disabled={request.status === "pending"}>
            Send reset link
          </Button>
        </form>
      )}
      <Link to="/login">Back to sign in</Link>
    </AuthPage>
  );
}

export function ResetPasswordPage() {
  const [params] = useSearchParams();
  const [password, setPassword] = useState("");
  const confirm = useApiMutation({ method: "post", path: "/api/v1/auth/password-reset/confirm" });
  const token = params.get("token");

  if (!token) {
    return (
      <AuthPage title="This link is incomplete">
        <p className={authStyles.note}>Open the full link from the email, or ask for a new one.</p>
        <Link to="/forgot-password">Request a new link</Link>
      </AuthPage>
    );
  }
  if (confirm.status === "success") {
    return (
      <AuthPage title="Password changed">
        <p className={authStyles.note}>Use your new password to sign in.</p>
        <Link to="/login">Sign in</Link>
      </AuthPage>
    );
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    confirm.submit({ body: { token: token as string, new_password: password } });
  }

  return (
    <AuthPage title="Choose a new password">
      <form className={authStyles.form} onSubmit={submit}>
        <TextField
          label="New password"
          type="password"
          name="new_password"
          autoComplete="new-password"
          required
          minLength={12}
          hint="Use at least 12 characters. A few unrelated words work well."
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          error={fieldError(confirm.problem, "new_password")}
        />
        <MutationFeedback mutation={confirm} />
        <Button type="submit" variant="primary" disabled={confirm.status === "pending"}>
          Set new password
        </Button>
      </form>
      <Link to="/forgot-password">Request a new link</Link>
    </AuthPage>
  );
}
