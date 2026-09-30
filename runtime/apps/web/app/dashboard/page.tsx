"use client";

import { useEffect, useState } from "react";

import { Badge, Card, EmptyState, ErrorBanner, Spinner } from "@/components/ui";
import {
  ApprovalRequestOut,
  AuditEventOut,
  ExecutionRecordOut,
  SlackIntegrationOut,
  api,
} from "@/lib/api";
import { getActiveWorkspaceId } from "@/lib/session";
import { useWorkspace } from "@/lib/workspace-context";

export default function DashboardPage() {
  const { me } = useWorkspace();
  const [approvals, setApprovals] = useState<ApprovalRequestOut[] | null>(null);
  const [executions, setExecutions] = useState<ExecutionRecordOut[] | null>(null);
  const [audit, setAudit] = useState<AuditEventOut[] | null>(null);
  const [slack, setSlack] = useState<SlackIntegrationOut | null | undefined>(undefined);
  const [error, setError] = useState("");

  const ws = getActiveWorkspaceId();

  useEffect(() => {
    let active = true;
    Promise.all([
      api.listApprovals("PENDING", ws).catch(() => [] as ApprovalRequestOut[]),
      api.listExecutions(ws).catch(() => [] as ExecutionRecordOut[]),
      api.listAuditEvents(ws).catch(() => [] as AuditEventOut[]),
      api.getSlackIntegration(ws).catch(() => null),
    ])
      .then(([a, e, aud, s]) => {
        if (!active) return;
        setApprovals(a);
        setExecutions(e);
        setAudit(aud);
        setSlack(s);
      })
      .catch((err: Error) => {
        if (active) setError(err.message);
      });
    return () => {
      active = false;
    };
  }, [ws]);

  if (error) return <ErrorBanner message={error} />;

  const pendingCount = approvals?.filter((a) => a.status === "PENDING").length ?? 0;
  const recentExec = executions?.slice(0, 5) ?? [];
  const recentAudit = audit?.slice(0, 5) ?? [];

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">{me.current_workspace?.name}</h1>
        <p className="mt-1 text-sm text-[var(--muted)]">
          Signed in as {me.user.email} with the {me.role} role.
        </p>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <MetricCard
          label="Pending approvals"
          value={approvals === null ? "—" : String(pendingCount)}
          tone={pendingCount > 0 ? "warning" : "success"}
        />
        <MetricCard
          label="Total executions"
          value={executions === null ? "—" : String(executions.length)}
          tone="neutral"
        />
        <MetricCard
          label="Audit events"
          value={audit === null ? "—" : String(audit.length)}
          tone="neutral"
        />
        <MetricCard
          label="Slack"
          value={slack === undefined ? "—" : slack ? "Connected" : "Not connected"}
          tone={slack ? "success" : "warning"}
        />
      </div>

      <Card
        title="Recent executions"
        description="The runtime's actual execution history."
      >
        {executions === null ? (
          <Spinner label="Loading executions" />
        ) : recentExec.length === 0 ? (
          <EmptyState
            title="No executions yet"
            description="When the runtime executes actions, they will appear here."
          />
        ) : (
          <table className="w-full text-left text-sm">
            <thead className="text-xs uppercase tracking-wide text-[var(--muted)]">
              <tr className="border-b border-[var(--border)]">
                <th className="pb-2 font-medium">Capability</th>
                <th className="pb-2 font-medium">Outcome</th>
                <th className="pb-2 font-medium">Reason</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[var(--border)]">
              {recentExec.map((ex) => (
                <tr key={ex.id}>
                  <td className="py-2.5 font-mono text-xs">{ex.capability}</td>
                  <td className="py-2.5">
                    <OutcomeBadge outcome={ex.outcome} />
                  </td>
                  <td className="py-2.5 text-[var(--muted)]">{ex.reason}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>

      <Card
        title="Recent audit events"
        description="What happened in the product."
      >
        {audit === null ? (
          <Spinner label="Loading audit" />
        ) : recentAudit.length === 0 ? (
          <EmptyState
            title="No audit events yet"
            description="Governance changes, approval decisions, and team changes will appear here."
          />
        ) : (
          <table className="w-full text-left text-sm">
            <thead className="text-xs uppercase tracking-wide text-[var(--muted)]">
              <tr className="border-b border-[var(--border)]">
                <th className="pb-2 font-medium">Event</th>
                <th className="pb-2 font-medium">Outcome</th>
                <th className="pb-2 font-medium">When</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[var(--border)]">
              {recentAudit.map((ev) => (
                <tr key={ev.id}>
                  <td className="py-2.5 font-mono text-xs">{ev.event_type}</td>
                  <td className="py-2.5">
                    <Badge
                      tone={
                        ev.outcome === "SUCCESS"
                          ? "success"
                          : ev.outcome === "DENIED"
                            ? "danger"
                            : "warning"
                      }
                    >
                      {ev.outcome}
                    </Badge>
                  </td>
                  <td className="py-2.5 text-[var(--muted)]">
                    {new Date(ev.created_at).toLocaleString()}
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

function MetricCard({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone: "success" | "warning" | "neutral";
}) {
  return (
    <div className="rounded-lg border border-[var(--border)] bg-[var(--surface)] p-4">
      <p className="text-xs uppercase tracking-wide text-[var(--muted)]">{label}</p>
      <p className="mt-1 text-2xl font-semibold">{value}</p>
      <div className="mt-2">
        <Badge tone={tone}>{tone === "success" ? "OK" : tone === "warning" ? "Attention" : "—"}</Badge>
      </div>
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
