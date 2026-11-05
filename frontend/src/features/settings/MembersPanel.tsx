import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useParams } from "react-router";
import { QueryState } from "../../components/ui/QueryState";
import { apiRequest } from "../../lib/api";
import styles from "../automation/Automation.module.css";

const ROLES = ["OWNER", "FINANCE_ADMIN"] as const;

/** Members and roles (E013-E015, E115). Role changes and removals are audited by the server. */
export function MembersPanel() {
  const { ws = "" } = useParams();
  const client = useQueryClient();
  const [note, setNote] = useState<string | null>(null);
  const members = useQuery({
    queryKey: ["members", ws],
    queryFn: () =>
      apiRequest(
        { method: "get", path: "/api/v1/workspaces/{ws}/members" },
        { path: { ws } },
      ),
  });

  async function changeRole(memberId: string, role: (typeof ROLES)[number]) {
    setNote(null);
    try {
      await apiRequest(
        {
          method: "patch",
          path: "/api/v1/workspaces/{ws}/members/{member_id}",
        },
        { path: { ws, member_id: memberId }, body: { role } },
      );
      await client.invalidateQueries({ queryKey: ["members", ws] });
      setNote("Role updated. The change is in the audit history.");
    } catch {
      setNote(
        "The role was not changed. A workspace must keep at least one owner.",
      );
    }
  }

  async function remove(memberId: string) {
    setNote(null);
    try {
      await apiRequest(
        {
          method: "delete",
          path: "/api/v1/workspaces/{ws}/members/{member_id}",
        },
        { path: { ws, member_id: memberId } },
        { idempotencyKey: crypto.randomUUID() },
      );
      await client.invalidateQueries({ queryKey: ["members", ws] });
      setNote("Member removed. The change is in the audit history.");
    } catch {
      setNote(
        "The member was not removed. A workspace must keep at least one owner.",
      );
    }
  }

  return (
    <div className={styles.page}>
      <h1 className={styles.title}>Members</h1>
      {note && <p role="status">{note}</p>}
      <QueryState query={members} label="members">
        <table className={styles.card}>
          <caption className="sr-only">Workspace members</caption>
          <thead>
            <tr>
              <th scope="col">Email</th>
              <th scope="col">Role</th>
              <th scope="col">Status</th>
              <th scope="col">
                <span className="sr-only">Actions</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {(members.data?.items ?? []).map((member) => (
              <tr key={member.id}>
                <td>{member.email}</td>
                <td>
                  <select
                    aria-label={`Role for ${member.email}`}
                    value={member.role}
                    onChange={(event) =>
                      void changeRole(
                        member.id,
                        event.target.value as (typeof ROLES)[number],
                      )
                    }
                  >
                    {ROLES.map((role) => (
                      <option key={role} value={role}>
                        {role}
                      </option>
                    ))}
                  </select>
                </td>
                <td>{member.status}</td>
                <td>
                  <button type="button" onClick={() => void remove(member.id)}>
                    Remove {member.email}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </QueryState>
    </div>
  );
}
