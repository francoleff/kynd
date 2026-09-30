"use client";

import { useEffect, useState } from "react";

import { Badge, Card, ErrorBanner, Spinner } from "@/components/ui";
import { ApiError, Member, api } from "@/lib/api";
import { getActiveWorkspaceId } from "@/lib/session";

export default function TeamPage() {
  const [members, setMembers] = useState<Member[] | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api
      .members(getActiveWorkspaceId())
      .then(setMembers)
      .catch((err: ApiError) => setError(err.message));
  }, []);

  if (error) return <ErrorBanner message={error} />;
  if (!members) return <Spinner label="Loading team" />;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">Team</h1>
        <p className="mt-1 text-sm text-[var(--muted)]">
          Everyone with access to this workspace, and what each role can do.
        </p>
      </div>

      <Card>
        <table className="w-full text-left text-sm">
          <thead className="text-xs uppercase tracking-wide text-[var(--muted)]">
            <tr className="border-b border-[var(--border)]">
              <th className="pb-2 font-medium">Member</th>
              <th className="pb-2 font-medium">Role</th>
              <th className="pb-2 font-medium">Joined</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-[var(--border)]">
            {members.map((member) => (
              <tr key={member.id}>
                <td className="py-3">
                  <p>{member.name ?? "—"}</p>
                  <p className="font-mono text-xs text-[var(--muted)]">
                    {member.email}
                  </p>
                </td>
                <td className="py-3">
                  <Badge tone={member.role === "OWNER" ? "success" : "neutral"}>
                    {member.role}
                  </Badge>
                </td>
                <td className="py-3 text-[var(--muted)]">
                  {new Date(member.created_at).toLocaleDateString()}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>

      <Card
        title="What each role can do"
        description="Enforced by the API on every request, not just hidden in the UI."
      >
        <dl className="space-y-3 text-sm">
          {[
            ["OWNER", "Everything, including billing and deleting the workspace."],
            ["ADMIN", "Configure integrations, governance, and the team."],
            ["OPERATOR", "Run permitted actions and approve those that need it."],
            ["VIEWER", "Read-only. Can see every decision Kynd made."],
          ].map(([role, description]) => (
            <div key={role} className="flex gap-3">
              <dt className="w-24 shrink-0">
                <Badge>{role}</Badge>
              </dt>
              <dd className="text-[var(--muted)]">{description}</dd>
            </div>
          ))}
        </dl>
      </Card>
    </div>
  );
}
