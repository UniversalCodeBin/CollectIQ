import { useQueryClient } from "@tanstack/react-query";
import { Lock, Mail } from "lucide-react";
import { type FormEvent, useEffect, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router";
import { SESSION_KEY } from "../../app/SessionGate";
import { Button } from "../../components/ui/Button";
import { fieldError, PasswordField, TextField } from "../../components/ui/Field";
import { MutationFeedback } from "../../components/ui/MutationFeedback";
import { useApiMutation } from "../../lib/api";
import { AuthPage, AuthSwitch, authStyles } from "./AuthPage";
import { afterSignIn } from "./routing";
import { checkEmail, clearError, type FieldErrors, focusFirstError } from "./validation";

export function LoginPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [errors, setErrors] = useState<FieldErrors>({});
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const client = useQueryClient();
  const login = useApiMutation({ method: "post", path: "/api/v1/auth/login" });
  const next = params.get("next");
  const signedIn = login.status === "success" ? login.data : undefined;
  const pending = login.status === "pending";

  useEffect(() => {
    if (!signedIn) return;
    client.removeQueries({ queryKey: SESSION_KEY });
    void navigate(afterSignIn(signedIn, next), {
      replace: true,
      state: signedIn.user.email_verified ? undefined : { email: signedIn.user.email },
    });
  }, [signedIn, next, client, navigate]);

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (pending) return;
    // Only the shape is checked here. Whether the account exists is the server's answer, and it
    // gives the same reply for a wrong password as for an unknown email.
    const found: FieldErrors = {
      email: checkEmail(email),
      password: password ? undefined : "Enter your password.",
    };
    setErrors(found);
    if (found.email || found.password) return focusFirstError(event.currentTarget, found);
    login.submit({ body: { email, password } });
  }

  return (
    <AuthPage title="Sign in" lead="Welcome back. Sign in to see what needs following up today.">
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
          error={errors.email ?? fieldError(login.problem, "email")}
        />
        <PasswordField
          label="Password"
          name="password"
          icon={Lock}
          autoComplete="current-password"
          required
          value={password}
          onChange={(event) => {
            setPassword(event.target.value);
            setErrors(clearError("password"));
          }}
          error={errors.password ?? fieldError(login.problem, "password")}
        />
        <div className={authStyles.row}>
          <Link to="/forgot-password">Forgot your password?</Link>
        </div>
        <MutationFeedback mutation={login} />
        <Button type="submit" variant="primary" size="lg" block busy={pending} disabled={pending}>
          Sign in
        </Button>
      </form>
      <AuthSwitch>
        New to CollectIQ? <Link to="/signup">Create an account</Link>
      </AuthSwitch>
    </AuthPage>
  );
}
