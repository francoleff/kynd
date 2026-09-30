"use client";

import { useEffect, useState } from "react";

import { Badge, Card, EmptyState, ErrorBanner, Spinner } from "@/components/ui";
import { Modal } from "@/components/modal";
import { Button, Field, Input } from "@/components/ui";
import {
  GovernancePreview,
  GovernanceRuleCreate,
  GovernanceRuleOut,
  SimulateRequest,
  SimulateResponse,
  WorkspaceCapabilityCreate,
  WorkspaceCapabilityOut,
  api,
  ApiError,
} from "@/lib/api";
import { getActiveWorkspaceId } from "@/lib/session";
import { useCan, useWorkspace } from "@/lib/workspace-context";

const RULE_TYPES = ["block_action_type", "block_capability", "require_param", "block_param_value"];

export default function ConstitutionPage() {
  const { me } = useWorkspace();
  const canUpdate = useCan("governance:update");
  const ws = getActiveWorkspaceId();
  const [capabilities, setCapabilities] = useState<WorkspaceCapabilityOut[] | null>(null);
  const [rules, setRules] = useState<GovernanceRuleOut[] | null>(null);
  const [preview, setPreview] = useState<GovernancePreview | null>(null);
  const [error, setError] = useState("");
  const [showCapModal, setShowCapModal] = useState(false);
  const [showRuleModal, setShowRuleModal] = useState(false);
  const [showSimulate, setShowSimulate] = useState(false);

  const load = async () => {
    const [caps, rules_, prev] = await Promise.all([
      api.listCapabilities(ws),
      api.listRules(ws),
      api.previewConstitution(ws).catch(() => null),
    ]);
    setCapabilities(caps);
    setRules(rules_);
    setPreview(prev);
  };

  useEffect(() => {
    load().catch((err: Error) => setError(err.message));
  }, [ws]);

  if (error) return <ErrorBanner message={error} />;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold">Constitution</h1>
          <p className="mt-1 text-sm text-[var(--muted)]">
            What Kynd can do, cannot do, and must ask a human about.
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="secondary" onClick={() => setShowSimulate(true)}>
            Simulate
          </Button>
          {canUpdate && (
            <>
              <Button variant="secondary" onClick={() => setShowCapModal(true)}>
                Add capability
              </Button>
              <Button onClick={() => setShowRuleModal(true)}>Add rule</Button>
            </>
          )}
        </div>
      </div>

      {preview && (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          <PreviewCard
            title="Allowed"
            items={preview.allowed}
            tone="success"
          />
          <PreviewCard
            title="Blocked capabilities"
            items={preview.blocked_capabilities}
            tone="danger"
          />
          <PreviewCard
            title="Blocked action types"
            items={preview.blocked_action_types}
            tone="danger"
          />
          <PreviewCard
            title="Approval required"
            items={preview.approval_required}
            tone="warning"
          />
        </div>
      )}

      <Card title="Capabilities" description="Actions this workspace can perform.">
        {capabilities === null ? (
          <Spinner label="Loading capabilities" />
        ) : capabilities.length === 0 ? (
          <EmptyState
            title="No capabilities yet"
            description="Add a capability to define what actions Kynd can govern."
          />
        ) : (
          <table className="w-full text-left text-sm">
            <thead className="text-xs uppercase tracking-wide text-[var(--muted)]">
              <tr className="border-b border-[var(--border)]">
                <th className="pb-2 font-medium">Name</th>
                <th className="pb-2 font-medium">Status</th>
                <th className="pb-2 font-medium">Max amount</th>
                <th className="pb-2 font-medium">Calls/day</th>
                <th className="pb-2 font-medium">Approval</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[var(--border)]">
              {capabilities.map((cap) => (
                <tr key={cap.id}>
                  <td className="py-2.5 font-mono text-xs">{cap.name}</td>
                  <td className="py-2.5">
                    <Badge tone={cap.enabled ? "success" : "neutral"}>
                      {cap.enabled ? "Enabled" : "Disabled"}
                    </Badge>
                  </td>
                  <td className="py-2.5 text-[var(--muted)]">
                    {cap.max_amount ?? "—"}
                  </td>
                  <td className="py-2.5 text-[var(--muted)]">
                    {cap.max_calls_per_day ?? "—"}
                  </td>
                  <td className="py-2.5">
                    {cap.requires_approval && <Badge tone="warning">Required</Badge>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>

      <Card title="Rules" description="Deterministic governance rules.">
        {rules === null ? (
          <Spinner label="Loading rules" />
        ) : rules.length === 0 ? (
          <EmptyState
            title="No rules yet"
            description="Add a rule to block an action type, require a parameter, or block values."
          />
        ) : (
          <table className="w-full text-left text-sm">
            <thead className="text-xs uppercase tracking-wide text-[var(--muted)]">
              <tr className="border-b border-[var(--border)]">
                <th className="pb-2 font-medium">Name</th>
                <th className="pb-2 font-medium">Type</th>
                <th className="pb-2 font-medium">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[var(--border)]">
              {rules.map((rule) => (
                <tr key={rule.id}>
                  <td className="py-2.5">{rule.name}</td>
                  <td className="py-2.5 font-mono text-xs">{rule.rule_type}</td>
                  <td className="py-2.5">
                    <Badge tone={rule.enabled ? "success" : "neutral"}>
                      {rule.enabled ? "Active" : "Inactive"}
                    </Badge>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>

      <CapabilityModal
        open={showCapModal}
        onClose={() => setShowCapModal(false)}
        onSaved={load}
      />
      <RuleModal
        open={showRuleModal}
        onClose={() => setShowRuleModal(false)}
        onSaved={load}
      />
      <SimulateModal
        open={showSimulate}
        onClose={() => setShowSimulate(false)}
      />
    </div>
  );
}

function PreviewCard({
  title,
  items,
  tone,
}: {
  title: string;
  items: string[];
  tone: "success" | "warning" | "danger";
}) {
  return (
    <div className="rounded-lg border border-[var(--border)] bg-[var(--surface)] p-4">
      <p className="text-xs uppercase tracking-wide text-[var(--muted)]">{title}</p>
      {items.length === 0 ? (
        <p className="mt-2 text-sm text-[var(--muted)]">None</p>
      ) : (
        <ul className="mt-2 flex flex-wrap gap-1.5">
          {items.map((item) => (
            <li key={item}>
              <Badge tone={tone}>{item}</Badge>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function CapabilityModal({
  open,
  onClose,
  onSaved,
}: {
  open: boolean;
  onClose: () => void;
  onSaved: () => void;
}) {
  const ws = getActiveWorkspaceId();
  const [name, setName] = useState("");
  const [maxAmount, setMaxAmount] = useState("");
  const [maxCalls, setMaxCalls] = useState("");
  const [requiresApproval, setRequiresApproval] = useState(false);
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  async function save() {
    setError("");
    setSaving(true);
    try {
      const data: WorkspaceCapabilityCreate = {
        name: name.trim(),
        enabled: true,
        requires_approval: requiresApproval,
      };
      if (maxAmount) data.max_amount = parseFloat(maxAmount);
      if (maxCalls) data.max_calls_per_day = parseInt(maxCalls, 10);
      await api.createCapability(data, ws);
      setName("");
      setMaxAmount("");
      setMaxCalls("");
      setRequiresApproval(false);
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
    <Modal open={open} onClose={onClose} title="Add capability">
      <div className="space-y-4">
        <ErrorBanner message={error} />
        <Field label="Name">
          <Input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="send_email"
          />
        </Field>
        <Field label="Max amount (optional)">
          <Input
            value={maxAmount}
            onChange={(e) => setMaxAmount(e.target.value)}
            placeholder="1000"
          />
        </Field>
        <Field label="Max calls per day (optional)">
          <Input
            value={maxCalls}
            onChange={(e) => setMaxCalls(e.target.value)}
            placeholder="100"
          />
        </Field>
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={requiresApproval}
            onChange={(e) => setRequiresApproval(e.target.checked)}
          />
          Requires human approval
        </label>
        <div className="flex justify-end gap-2">
          <Button variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button onClick={save} loading={saving} disabled={!name.trim()}>
            Save
          </Button>
        </div>
      </div>
    </Modal>
  );
}

function RuleModal({
  open,
  onClose,
  onSaved,
}: {
  open: boolean;
  onClose: () => void;
  onSaved: () => void;
}) {
  const ws = getActiveWorkspaceId();
  const [name, setName] = useState("");
  const [ruleType, setRuleType] = useState(RULE_TYPES[0]);
  const [config, setConfig] = useState("{}");
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  async function save() {
    setError("");
    setSaving(true);
    try {
      let parsedConfig: Record<string, unknown> = {};
      try {
        parsedConfig = JSON.parse(config);
      } catch {
        setError("Config must be valid JSON");
        setSaving(false);
        return;
      }
      const data: GovernanceRuleCreate = {
        name: name.trim(),
        rule_type: ruleType,
        config: parsedConfig,
        enabled: true,
      };
      await api.createRule(data, ws);
      setName("");
      setConfig("{}");
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
    <Modal open={open} onClose={onClose} title="Add rule">
      <div className="space-y-4">
        <ErrorBanner message={error} />
        <Field label="Name">
          <Input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Block payments"
          />
        </Field>
        <Field label="Rule type">
          <select
            value={ruleType}
            onChange={(e) => setRuleType(e.target.value)}
            className="w-full rounded-md border border-[var(--border)] bg-[var(--surface)] px-3 py-2 text-sm"
          >
            {RULE_TYPES.map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Config (JSON)">
          <textarea
            value={config}
            onChange={(e) => setConfig(e.target.value)}
            rows={4}
            className="w-full rounded-md border border-[var(--border)] bg-[var(--surface)] px-3 py-2 font-mono text-xs"
          />
        </Field>
        <div className="flex justify-end gap-2">
          <Button variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button onClick={save} loading={saving} disabled={!name.trim()}>
            Save
          </Button>
        </div>
      </div>
    </Modal>
  );
}

function SimulateModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const ws = getActiveWorkspaceId();
  const [type, setType] = useState("");
  const [capability, setCapability] = useState("");
  const [amount, setAmount] = useState("");
  const [result, setResult] = useState<SimulateResponse | null>(null);
  const [error, setError] = useState("");
  const [testing, setTesting] = useState(false);

  async function simulate() {
    setError("");
    setResult(null);
    setTesting(true);
    try {
      const data: SimulateRequest = {
        type: type.trim(),
        capability: capability.trim(),
        amount: amount ? parseFloat(amount) : null,
      };
      const res = await api.simulateAction(data, ws);
      setResult(res);
    } catch (err) {
      const apiError = err as ApiError;
      setError(apiError.message);
    } finally {
      setTesting(false);
    }
  }

  return (
    <Modal open={open} onClose={onClose} title="Simulate action">
      <div className="space-y-4">
        <ErrorBanner message={error} />
        <Field label="Action type">
          <Input value={type} onChange={(e) => setType(e.target.value)} placeholder="send" />
        </Field>
        <Field label="Capability">
          <Input
            value={capability}
            onChange={(e) => setCapability(e.target.value)}
            placeholder="send_email"
          />
        </Field>
        <Field label="Amount (optional)">
          <Input value={amount} onChange={(e) => setAmount(e.target.value)} placeholder="100" />
        </Field>
        <div className="flex justify-end gap-2">
          <Button variant="secondary" onClick={onClose}>
            Close
          </Button>
          <Button onClick={simulate} loading={testing} disabled={!type.trim() || !capability.trim()}>
            Test
          </Button>
        </div>
        {result && (
          <div
            className={`rounded-md border p-3 text-sm ${
              result.allowed
                ? "border-[var(--success)] bg-[var(--success)]/10"
                : "border-[var(--danger)] bg-[var(--danger)]/10"
            }`}
          >
            <p className="font-medium">
              {result.allowed ? "Allowed" : "Blocked"}
            </p>
            <p className="mt-1 text-[var(--muted)]">{result.reason}</p>
          </div>
        )}
      </div>
    </Modal>
  );
}
