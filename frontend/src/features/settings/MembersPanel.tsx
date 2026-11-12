import { useQuery, useQueryClient } from "@tanstack/react-query";
import { type FormEvent, useEffect, useState } from "react";
import { useParams } from "react-router";
import { Button } from "../../components/ui/Button";
import { Dialog } from "../../components/ui/Dialog";
import { fieldError, SelectField, TextField } from "../../components/ui/Field";
import { MutationFeedback } from "../../components/ui/MutationFeedback";
import { Section } from "../../components/ui/Page";
import { QueryState } from "../../components/ui/QueryState";
import { ApiProblem, apiRequest, useApiMutation } from "../../lib/api";
import type { components } from "../../lib/api-types";
import { formatDate } from "../../lib/format";
import styles from "./Settings.module.css";

type Member = components["schemas"]["MemberOut"];
type Role = components["schemas"]["RoleEnum"];

const ROLES: { value: Role; text: string }[] = [
  { value: "OWNER", text: "Owner" },
  { value: "FINANCE_ADMIN", text: "Finance admin" },
];

const STATUS_TEXT: Record<string, string> = {
  ACTIVE: "Active",
  INVITED: "Invited, not yet joined",
  REMOVED: "Removed",
  SUSPENDED: "Suspended",
};

/** Invite a teammate (E014). The server queues the email; the person joins through the link in it. */
function InviteForm({ ws }: { ws: string }) {
  const invite = useApiMutation({ method: "post", path: "/api/v1/workspaces/{ws}/invitations" }, { idempotent: true });
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<Role>("FINANCE_ADMIN");
  const [local, setLocal] = useState<ApiProblem | null>(null);
  const pending = invite.status === "pending";
  const sent = invite.status === "success" ? invite.data : undefined;

  function submit(event: FormEvent) {
    event.preventDefault();
    if (pending) return;
    const address = email.trim();
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(address)) {
      return setLocal(
        new ApiProblem({
          status: 400,
          code: "VALIDATION_FAILED",
          detail: "",
          correlationId: null,
          errors: [{ field: "email", message: "Enter the person's email address, such as name@company.com." }],
        }),
      );
    }
    setLocal(null);
    invite.submit({ path: { ws }, body: { email: address, role } });
  }

  useEffect(() => {
    if (invite.status === "success") setEmail("");
  }, [invite.status]);

  return (
    <Section
      title="Invite someone"
      description="They get an email with a link to join this workspace. Only owners can invite, change roles and edit your business details."
      level={3}
    >
      <form className={styles.form} onSubmit={submit} noValidate>
        <TextField
          label="Email address"
          type="email"
          autoComplete="off"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          error={fieldError(local, "email") ?? fieldError(invite.problem, "email")}
        />
        <SelectField label="Role" value={role} onChange={(e) => setRole(e.target.value as Role)}>
          {ROLES.map((r) => (
            <option key={r.value} value={r.value}>
              {r.text}
            </option>
          ))}
        </SelectField>
        <MutationFeedback mutation={invite} />
        {sent && (
          <p role="status" className={styles.done}>
            Invitation created for {sent.email}. The email with the link is on its way; the link works until{" "}
            {formatDate(sent.expires_at)}.
          </p>
        )}
        <div className={styles.actions}>
          <Button variant="primary" type="submit" busy={pending} aria-disabled={pending || undefined}>
            Send invitation
          </Button>
        </div>
      </form>
    </Section>
  );
}

function RemoveDialog({
  member,
  busy,
  onConfirm,
  onClose,
}: {
  member: Member;
  busy: boolean;
  onConfirm: () => void;
  onClose: () => void;
}) {
  return (
    <Dialog open onClose={onClose} title="Remove this member?" destructive>
      <div className={styles.dialogBody}>
        <p className={styles.note}>
          <strong>{member.email}</strong> will lose access to this workspace straight away. What they did here stays on
          record. You can invite them again later.
        </p>
        <div className={styles.actions}>
          <Button variant="danger" busy={busy} aria-disabled={busy || undefined} onClick={() => !busy && onConfirm()}>
            Remove member
          </Button>
          <Button data-cancel onClick={onClose}>
            Keep member
          </Button>
        </div>
      </div>
    </Dialog>
  );
}

/** Members and roles (E013-E015, E115). Role changes and removals are audited by the server. */
export function MembersPanel() {
  const { ws = "" } = useParams();
  const client = useQueryClient();
  const [note, setNote] = useState<string | null>(null);
  const [removing, setRemoving] = useState<Member | null>(null);
  const [busy, setBusy] = useState(false);
  const members = useQuery({
    queryKey: ["members", ws],
    queryFn: () => apiRequest({ method: "get", path: "/api/v1/workspaces/{ws}/members" }, { path: { ws } }),
  });
  const items = members.data?.items ?? [];

  async function changeRole(memberId: string, role: Role) {
    setNote(null);
    try {
      await apiRequest(
        { method: "patch", path: "/api/v1/workspaces/{ws}/members/{member_id}" },
        { path: { ws, member_id: memberId }, body: { role } },
      );
      await client.invalidateQueries({ queryKey: ["members", ws] });
      setNote("Role updated. The change is in the audit history.");
    } catch {
      setNote("The role was not changed. A workspace must keep at least one owner.");
    }
  }

  async function remove(member: Member) {
    setNote(null);
    setBusy(true);
    try {
      await apiRequest(
        { method: "delete", path: "/api/v1/workspaces/{ws}/members/{member_id}" },
        { path: { ws, member_id: member.id } },
        { idempotencyKey: crypto.randomUUID() },
      );
      await client.invalidateQueries({ queryKey: ["members", ws] });
      setNote("Member removed. The change is in the audit history.");
    } catch {
      setNote("The member was not removed. A workspace must keep at least one owner.");
    } finally {
      setBusy(false);
      setRemoving(null);
    }
  }

  return (
    <>
      <Section
        title="Members"
        description="Everyone who can sign in to this workspace. A workspace always keeps at least one owner."
      >
        {note && (
          <p role="status" className={styles.note}>
            {note}
          </p>
        )}
        <QueryState query={members} label="members">
          <ul className={styles.list} aria-label="Workspace members">
            {items.map((member) => (
              <li key={member.id} className={styles.memberRow}>
                <div className={styles.who}>
                  <p className={styles.email}>{member.email}</p>
                  <p className={styles.muted}>{STATUS_TEXT[member.status] ?? member.status}</p>
                </div>
                <select
                  className={styles.select}
                  aria-label={`Role for ${member.email}`}
                  value={member.role}
                  onChange={(event) => void changeRole(member.id, event.target.value as Role)}
                >
                  {ROLES.map((role) => (
                    <option key={role.value} value={role.value}>
                      {role.text}
                    </option>
                  ))}
                </select>
                <Button
                  variant="quiet"
                  size="sm"
                  aria-label={`Remove ${member.email}`}
                  onClick={() => setRemoving(member)}
                >
                  Remove
                </Button>
              </li>
            ))}
          </ul>
        </QueryState>
      </Section>
      <InviteForm ws={ws} />
      {removing && (
        <RemoveDialog
          member={removing}
          busy={busy}
          onConfirm={() => void remove(removing)}
          onClose={() => !busy && setRemoving(null)}
        />
      )}
    </>
  );
}
