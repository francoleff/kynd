"use client";

import { useEffect, useState } from "react";

import { Badge, Card, EmptyState, ErrorBanner, Spinner } from "@/components/ui";
import { AuditEventOut, api } from "@/lib/api";
import { getActiveWorkspaceId } from "@/lib/session";

export default function AuditPage() {
  const ws = getActiveWorkspaceId();
  const [events, setEvents] = useState<AuditEventOut[] | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api
      .listAuditEvents(ws)
      .then(setEvents)
      .catch((err: Error) => setError(err.message));
  }, [ws]);

  if (error) return <ErrorBanner message={error} />;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">Audit</h1>
        <p className="mt-1 text-sm text-[var(--muted)]">
          What happened in the product. Distinct from the runtime's execution log.
        </p>
      </div>

      <Card>
        {events === null ? (
          <Spinner label="Loading audit events" />
        ) : events.length === 0 ? (
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
                <th className="pb-2 font-medium">Resource</th>
                <th className="pb-2 font-medium">Actor</th>
                <th className="pb-2 font-medium">When</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[var(--border)]">
              {events.map((ev) => (
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
                    {ev.resource_type}
                    {ev.resource_id ? `:${ev.resource_id.slice(0, 8)}` : ""}
                  </td>
                  <td className="py-2.5 text-[var(--muted)]">
                    {ev.actor_user_id ? ev.actor_user_id.slice(0, 8) : "—"}
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
