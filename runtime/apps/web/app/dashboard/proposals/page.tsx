"use client";

import { useEffect, useState } from "react";

import { Badge, Card, EmptyState, ErrorBanner, Spinner } from "@/components/ui";
import { Button, Field, Input } from "@/components/ui";
import { Modal } from "@/components/modal";
import { AIProposalOut, api, ApiError } from "@/lib/api";
import { getActiveWorkspaceId } from "@/lib/session";
import { useCan } from "@/lib/workspace-context";

export default function ProposalsPage() {
  const ws = getActiveWorkspaceId();
  const canPropose = useCan("action:propose");
  const [proposals, setProposals] = useState<AIProposalOut[] | null>(null);
  const [error, setError] = useState("");
  const [showGenerate, setShowGenerate] = useState(false);

  const load = async () => {
    const data = await api.listProposals(ws);
    setProposals(data);
  };

  useEffect(() => {
    let active = true;
    api
      .listProposals(ws)
      .then((data) => {
        if (active) setProposals(data);
      })
      .catch((err: Error) => {
        if (active) setError(err.message);
      });
    return () => {
      active = false;
    };
  }, [ws]);

  if (error) return <ErrorBanner message={error} />;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold">Proposals</h1>
          <p className="mt-1 text-sm text-[var(--muted)]">
            AI-generated proposals. Routed proposals go to the Approval Center.
          </p>
        </div>
        {canPropose && (
          <Button onClick={() => setShowGenerate(true)}>Generate proposal</Button>
        )}
      </div>

      <Card>
        {proposals === null ? (
          <Spinner label="Loading proposals" />
        ) : proposals.length === 0 ? (
          <EmptyState
            title="No proposals yet"
            description="Generate a proposal to see AI-suggested actions."
          />
        ) : (
          <table className="w-full text-left text-sm">
            <thead className="text-xs uppercase tracking-wide text-[var(--muted)]">
              <tr className="border-b border-[var(--border)]">
                <th className="pb-2 font-medium">Intent</th>
                <th className="pb-2 font-medium">Capability</th>
                <th className="pb-2 font-medium">Status</th>
                <th className="pb-2 font-medium">Routed</th>
                <th className="pb-2 font-medium">When</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[var(--border)]">
              {proposals.map((p) => (
                <tr key={p.id}>
                  <td className="max-w-xs truncate py-2.5">{p.intent}</td>
                  <td className="py-2.5 font-mono text-xs">{p.capability ?? "—"}</td>
                  <td className="py-2.5">
                    <ProposalStatusBadge status={p.status} />
                  </td>
                  <td className="py-2.5 text-[var(--muted)]">
                    {p.approval_request_id ? "Yes" : "—"}
                  </td>
                  <td className="py-2.5 text-[var(--muted)]">
                    {new Date(p.created_at).toLocaleString()}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>

      <GenerateProposalModal
        open={showGenerate}
        onClose={() => setShowGenerate(false)}
        onSaved={load}
      />
    </div>
  );
}

function ProposalStatusBadge({ status }: { status: string }) {
  const tone =
    status === "ROUTED_TO_APPROVAL"
      ? "success"
      : status === "REJECTED"
        ? "danger"
        : "neutral";
  return <Badge tone={tone}>{status}</Badge>;
}

function GenerateProposalModal({
  open,
  onClose,
  onSaved,
}: {
  open: boolean;
  onClose: () => void;
  onSaved: () => void;
}) {
  const ws = getActiveWorkspaceId();
  const [intent, setIntent] = useState("");
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  async function generate() {
    setError("");
    setSaving(true);
    try {
      await api.generateProposal({ intent: intent.trim() }, ws);
      setIntent("");
      onSaved();
      onClose();
    } catch (err) {
      const apiError = err as ApiError;
      setError(apiError.message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <Modal open={open} onClose={onClose} title="Generate proposal">
      <div className="space-y-4">
        <ErrorBanner message={error} />
        <Field label="Intent">
          <textarea
            value={intent}
            onChange={(e) => setIntent(e.target.value)}
            rows={3}
            placeholder="Send a welcome email to new users"
            className="w-full rounded-md border border-[var(--border)] bg-[var(--surface)] px-3 py-2 text-sm"
          />
        </Field>
        <p className="text-xs text-[var(--muted)]">
          The AI proposes. Kynd decides. Routed proposals require human approval.
        </p>
        <div className="flex justify-end gap-2">
          <Button variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button onClick={generate} loading={saving} disabled={!intent.trim()}>
            Generate
          </Button>
        </div>
      </div>
    </Modal>
  );
}
