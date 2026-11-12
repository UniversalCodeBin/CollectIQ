import { Lock, Mail } from "lucide-react";
import { type FormEvent, useState } from "react";
import { Link, Navigate } from "react-router";
import { Button } from "../../components/ui/Button";
import { fieldError, PasswordField, TextField } from "../../components/ui/Field";
import { MutationFeedback } from "../../components/ui/MutationFeedback";
import { useApiMutation } from "../../lib/api";
import { AuthPage, AuthSwitch, authStyles } from "./AuthPage";
import {
  checkEmail,
  checkNewPassword,
  clearError,
  type FieldErrors,
  focusFirstError,
  PasswordRules,
} from "./validation";

export function SignupPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [errors, setErrors] = useState<FieldErrors>({});
  const register = useApiMutation(
    { method: "post", path: "/api/v1/auth/register" },
    { idempotent: true, secretBody: true },
  );
  const pending = register.status === "pending";

  // The server answers the same way whether or not the address is already registered, so the next
  // screen says "check your email" in both cases rather than revealing which accounts exist.
  if (register.status === "success") return <Navigate to="/verify-email" replace state={{ email }} />;

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (pending) return;
    const found: FieldErrors = {
      email: checkEmail(email),
      password: checkNewPassword(password, email),
    };
    setErrors(found);
    if (found.email || found.password) return focusFirstError(event.currentTarget, found);
    register.submit({ body: { email, password } });
  }

  return (
    <AuthPage title="Create your account" lead="Start with your work email. You'll set up your business next.">
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
          error={errors.email ?? fieldError(register.problem, "email")}
        />
        <PasswordField
          label="Password"
          name="password"
          icon={Lock}
          autoComplete="new-password"
          required
          minLength={12}
          maxLength={128}
          hint="Use at least 12 characters. A few unrelated words work well."
          value={password}
          onChange={(event) => {
            setPassword(event.target.value);
            setErrors(clearError("password"));
          }}
          error={errors.password ?? fieldError(register.problem, "password")}
        />
        <PasswordRules password={password} email={email} />
        <MutationFeedback mutation={register} />
        {register.status !== "unknown" && (
          <Button type="submit" variant="primary" size="lg" block busy={pending} disabled={pending}>
            Create account
          </Button>
        )}
      </form>
      <p className={authStyles.note}>
        CollectIQ shows who owes you what and helps you follow up, with you approving each step. It is not an invoicing
        tool, a payment processor or a collections agency.
      </p>
      <AuthSwitch>
        Already have an account? <Link to="/login">Sign in</Link>
      </AuthSwitch>
    </AuthPage>
  );
}
