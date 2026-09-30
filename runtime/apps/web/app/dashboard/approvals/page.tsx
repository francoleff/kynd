"use client";

import { useEffect, useState } from "react";

import { Badge, Card, EmptyState, ErrorBanner, Spinner } from "@/components/ui";
import { Button, Field, Input } from "@/components/ui";
import { Modal } from "@/components/modal";
import { ApprovalRequestOut, api, ApiError } from "@/lib/api";
import { getActiveWorkspaceId } from "@/lib/session";
import { useCan } from "@/lib/workspace-context";

export default function ApprovalsPage() {
  const ws = getActiveWorkspaceId();
  const canDecide = useCan("approval:decide");
  const [approvals, setApprovals] = useState<ApprovalRequestOut[] | null>(null);
  const [error, setError] = useState("");
  const [filter, setFilter] = useState<string>("PENDING");

  const load = async () => {
    const data = await api.listApprovals(filter || undefined, ws);
    setApprovals(data);
  };

  useEffect(() => {
    load().catch((err: Error) => setError(err.message));
  }, [ws, filter]);

  if (error) return <ErrorBanner message={error} />;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold">Approvals</h1>
          <p className="mt-1 text-sm text-[var(--muted)]">
            Human-in-the-loop decisions. Approve or reject pending requests.
          </p>
        </div>
        <div className="flex gap-2">
          {["PENDING", "APPROVED", "REJECTED", "EXPIRED", ""].map((s) => (
            <button
              key={s}
              onClick={() => setFilter(s)}
              className={`rounded-md px-3 py-1.5 text-sm transition-colors ${
                filter === s
                  ? "bg-[var(--surface-raised)] text-[var(--foreground)]"
                  : "text-[var(--muted)] hover:text-[var(--foreground)]"
              }`}
            >
              {s || "All"}
            </button>
          ))}
        </div>
      </div>

      <Card>
        {approvals === null ? (
          <Spinner label="Loading approvals" />
        ) : approvals.length === 0 ? (
          <EmptyState
            title="No approvals"
            description="No approval requests match this filter."
          />
        ) : (
          <table className="w-full text-left text-sm">
            <thead className="text-xs uppercase tracking-wide text-[var(--muted)]">
              <tr className="border-b border-[var(--border)]">
                <th className="pb-2 font-medium">Capability</th>
                <th className="pb-2 font-medium">Action</th>
                <th className="pb-2 font-medium">Target</th>
                <th className="pb-2 font-medium">Status</th>
                <th className="pb-2 font-medium">Requested</th>
                <th className="pb-2 font-medium"></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[var(--border)]">
              {approvals.map((a) => (
                <tr key={a.id}>
                  <td className="py-2.5 font-mono text-xs">{a.capability}</td>
                  <td className="py-2.5 text-[var(--muted)]">{a.action_type ?? "—"}</td>
                  <td className="py-2.5 text-[var(--muted)]">{a.target ?? "—"}</td>
                  <td className="py-2.5">
                    <ApprovalStatusBadge status={a.status} />
                  </td>
                  <td className="py-2.5 text-[var(--muted)]">
                    {new Date(a.created_at).toLocaleString()}
                  </td>
                  <td className="py-2.5">
                    {a.status === "PENDING" && canDecide && (
                      <DecisionControls approval={a} onDecided={load} />
                    )}
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

function ApprovalStatusBadge({ status }: { status: string }) {
  const tone =
    status === "APPROVED"
      ? "success"
      : status === "REJECTED"
        ? "danger"
        : status === "PENDING"
          ? "warning"
          : "neutral";
  return <Badge tone={tone}>{status}</Badge>;
}

function DecisionControls({
  approval,
  onDecided,
}: {
  approval: ApprovalRequestOut;
  onDecided: () => void;
}) {
  const ws = getActiveWorkspaceId();
  const [showModal, setShowModal] = useState<"approve" | "reject" | null>(null);
  const [note, setNote] = useState("");
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  async function decide(kind: "approve" | "reject") {
    setError("");
    setSaving(true);
    try {
      if (kind === "approve") {
        await api.approveRequest(approval.id, { note: note || undefined }, ws);
      } else {
        await api.rejectRequest(approval.id, { note: note || undefined }, ws);
      }
      setNote("");
      setShowModal(null);
      onDecided();
    } catch (err) {
      const apiError = err as ApiError;
      setError(apiError.message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <>
      <div className="flex gap-2">
        <Button onClick={() => setShowModal("approve")}>Approve</Button>
        <Button variant="danger" onClick={() => setShowModal("reject")}>Reject</Button>
      </div>
      <Modal
        open={showModal !== null}
        onClose={() => setShowModal(null)}
        title={showModal === "approve" ? "Approve request" : "Reject request"}
      >
        <div className="space-y-4">
          <ErrorBanner message={error} />
          <div className="rounded-md bg-[var(--surface-raised)] p-3 text-sm">
            <p>
              <span className="text-[var(--muted)]">Capability:</span>{" "}
              {approval.capability}
            </p>
            {approval.action_type && (
              <p>
                <span className="text-[var(--muted)]">Action:</span>{" "}
                {approval.action_type}
              </p>
            )}
            {approval.target && (
              <p>
                <span className="text-[var(--muted)]">Target:</span>{" "}
                {approval.target}
              </p>
            )}
            {approval.reason && (
              <p>
                <span className="text-[var(--muted)]">Reason:</span>{" "}
                {approval.reason}
              </p>
            )}
          </div>
          <Field label="Note (optional)">
            <Input value={note} onChange={(e) => setNote(e.target.value)} />
          </Field>
          <div className="flex justify-end gap-2">
            <Button variant="secondary" onClick={() => setShowModal(null)}>
              Cancel
            </Button>
            <Button
              variant={showModal === "approve" ? "primary" : "danger"}
              onClick={() => decide(showModal!)}
              loading={saving}
            >
              {showModal === "approve" ? "Approve" : "Reject"}
            </Button>
          </div>
        </div>
      </Modal>
    </>
  );
}
