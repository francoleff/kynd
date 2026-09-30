"use client";

import { useEffect, useState } from "react";

import { Badge, Card, EmptyState, ErrorBanner, Spinner } from "@/components/ui";
import { ExecutionRecordOut, api } from "@/lib/api";
import { getActiveWorkspaceId } from "@/lib/session";

export default function ExecutionsPage() {
  const ws = getActiveWorkspaceId();
  const [executions, setExecutions] = useState<ExecutionRecordOut[] | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api
      .listExecutions(ws)
      .then(setExecutions)
      .catch((err: Error) => setError(err.message));
  }, [ws]);

  if (error) return <ErrorBanner message={error} />;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">Executions</h1>
        <p className="mt-1 text-sm text-[var(--muted)]">
          Read-only history from the runtime. Proposals and approvals are separate.
        </p>
      </div>

      <Card>
        {executions === null ? (
          <Spinner label="Loading executions" />
        ) : executions.length === 0 ? (
          <EmptyState
            title="No executions yet"
            description="When the runtime executes actions, they will appear here."
          />
        ) : (
          <table className="w-full text-left text-sm">
            <thead className="text-xs uppercase tracking-wide text-[var(--muted)]">
              <tr className="border-b border-[var(--border)]">
                <th className="pb-2 font-medium">ID</th>
                <th className="pb-2 font-medium">Capability</th>
                <th className="pb-2 font-medium">Action</th>
                <th className="pb-2 font-medium">Outcome</th>
                <th className="pb-2 font-medium">Reason</th>
                <th className="pb-2 font-medium">When</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[var(--border)]">
              {executions.map((ex) => (
                <tr key={ex.id}>
                  <td className="py-2.5 font-mono text-xs">{ex.id}</td>
                  <td className="py-2.5 font-mono text-xs">{ex.capability}</td>
                  <td className="py-2.5 text-[var(--muted)]">{ex.action_type ?? "—"}</td>
                  <td className="py-2.5">
                    <OutcomeBadge outcome={ex.outcome} />
                  </td>
                  <td className="py-2.5 text-[var(--muted)]">{ex.reason}</td>
                  <td className="py-2.5 text-[var(--muted)]">
                    {new Date(ex.ts * 1000).toLocaleString()}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>
    </div>
  );
}

function OutcomeBadge({ outcome }: { outcome: string }) {
  const tone =
    outcome === "SUCCEEDED"
      ? "success"
      : outcome === "BLOCKED"
        ? "danger"
        : outcome === "FAILED"
          ? "danger"
          : "neutral";
  return <Badge tone={tone}>{outcome}</Badge>;
}
