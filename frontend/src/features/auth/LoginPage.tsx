import { useQueryClient } from "@tanstack/react-query";
import { type FormEvent, useEffect, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router";
import { SESSION_KEY } from "../../app/SessionGate";
import { Button } from "../../components/ui/Button";
import { fieldError, TextField } from "../../components/ui/Field";
import { MutationFeedback } from "../../components/ui/MutationFeedback";
import { useApiMutation } from "../../lib/api";
import { AuthPage, authStyles } from "./AuthPage";
import { afterSignIn } from "./routing";

export function LoginPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const client = useQueryClient();
  const login = useApiMutation({ method: "post", path: "/api/v1/auth/login" });
  const next = params.get("next");
  const signedIn = login.status === "success" ? login.data : undefined;

  useEffect(() => {
    if (!signedIn) return;
    client.removeQueries({ queryKey: SESSION_KEY });
    void navigate(afterSignIn(signedIn, next), {
      replace: true,
      state: signedIn.user.email_verified ? undefined : { email: signedIn.user.email },
    });
  }, [signedIn, next, client, navigate]);

  function submit(event: FormEvent) {
    event.preventDefault();
    login.submit({ body: { email, password } });
  }

  return (
    <AuthPage title="Sign in">
      <form className={authStyles.form} onSubmit={submit}>
        <TextField
          label="Email"
          type="email"
          name="email"
          autoComplete="username"
          required
          value={email}
          onChange={(event) => setEmail(event.target.value)}
          error={fieldError(login.problem, "email")}
        />
        <TextField
          label="Password"
          type="password"
          name="password"
          autoComplete="current-password"
          required
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          error={fieldError(login.problem, "password")}
        />
        <MutationFeedback mutation={login} />
        <Button type="submit" variant="primary" disabled={login.status === "pending"}>
          Sign in
        </Button>
      </form>
      <div className={authStyles.links}>
        <Link to="/forgot-password">Forgot your password?</Link>
        <Link to="/signup">Create an account</Link>
      </div>
    </AuthPage>
  );
}
