type Who = {
  user: { email_verified: boolean };
  workspaces: readonly { id: string }[];
};

/** A `next` address is only followed when it stays inside this app. */
export function safeNext(next: string | null): string | null {
  if (!next || !next.startsWith("/")) return null;
  const base = "http://collectiq.invalid";
  try {
    return new URL(next, base).origin === base ? next : null;
  } catch {
    return null;
  }
}

export function homeFor({ user, workspaces }: Who): string {
  if (!user.email_verified) return "/verify-email";
  const first = workspaces[0];
  return first ? `/w/${first.id}/dashboard` : "/onboarding/workspace";
}

export function afterSignIn(who: Who, next: string | null): string {
  return who.user.email_verified ? (safeNext(next) ?? homeFor(who)) : homeFor(who);
}
