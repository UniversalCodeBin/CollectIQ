import { type FormEvent, useState } from "react";
import { Link, Navigate } from "react-router";
import { Button } from "../../components/ui/Button";
import { fieldError, TextField } from "../../components/ui/Field";
import { MutationFeedback } from "../../components/ui/MutationFeedback";
import { useApiMutation } from "../../lib/api";
import { AuthPage, authStyles } from "./AuthPage";

export function SignupPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const register = useApiMutation(
    { method: "post", path: "/api/v1/auth/register" },
    { idempotent: true, secretBody: true },
  );

  if (register.status === "success") return <Navigate to="/verify-email" replace state={{ email }} />;

  function submit(event: FormEvent) {
    event.preventDefault();
    register.submit({ body: { email, password } });
  }

  return (
    <AuthPage title="Create your account">
      <p className={authStyles.note}>
        CollectIQ shows who owes you what and helps you follow up, with you approving each step. It is not an
        invoicing tool, a payment processor or a collections agency.
      </p>
      <form className={authStyles.form} onSubmit={submit}>
        <TextField
          label="Email"
          type="email"
          name="email"
          autoComplete="username"
          required
          value={email}
          onChange={(event) => setEmail(event.target.value)}
          error={fieldError(register.problem, "email")}
        />
        <TextField
          label="Password"
          type="password"
          name="password"
          autoComplete="new-password"
          required
          minLength={12}
          hint="Use at least 12 characters. A few unrelated words work well."
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          error={fieldError(register.problem, "password")}
        />
        <MutationFeedback mutation={register} />
        {register.status !== "unknown" && (
          <Button type="submit" variant="primary" disabled={register.status === "pending"}>
            Create account
          </Button>
        )}
      </form>
      <p className={authStyles.note}>
        Already have an account? <Link to="/login">Sign in</Link>
      </p>
    </AuthPage>
  );
}
