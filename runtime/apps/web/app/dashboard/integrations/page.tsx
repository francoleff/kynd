"use client";

import { useEffect, useState } from "react";

import { Badge, Card, EmptyState, ErrorBanner, Spinner } from "@/components/ui";
import { Button, Field, Input } from "@/components/ui";
import { Modal } from "@/components/modal";
import { api, ApiError, SlackConnectRequest, SlackIntegrationOut, SlackTestResult } from "@/lib/api";
import { getActiveWorkspaceId } from "@/lib/session";
import { useCan } from "@/lib/workspace-context";

export default function IntegrationsPage() {
  const ws = getActiveWorkspaceId();
  const canConnect = useCan("integration:connect");
  const canDisconnect = useCan("integration:disconnect");
  const canTest = useCan("integration:test");
  const [slack, setSlack] = useState<SlackIntegrationOut | null | undefined>(undefined);
  const [error, setError] = useState("");
  const [showConnect, setShowConnect] = useState(false);

  const load = async () => {
    const data = await api.getSlackIntegration(ws);
    setSlack(data);
  };

  useEffect(() => {
    load().catch((err: Error) => setError(err.message));
  }, [ws]);

  if (error) return <ErrorBanner message={error} />;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold">Integrations</h1>
          <p className="mt-1 text-sm text-[var(--muted)]">
            External systems connected to this workspace.
          </p>
        </div>
      </div>

      <Card
        title="Slack"
        description="Connect a Slack workspace."
        action={
          slack === undefined ? (
            <Spinner label="Loading" />
          ) : slack === null ? (
            canConnect && (
              <Button onClick={() => setShowConnect(true)}>Connect</Button>
            )
          ) : (
            <div className="flex gap-2">
              {canTest && (
                <TestButton
                  onResult={(r) => {
                    setError(r.ok ? "" : r.error ?? "Test failed");
                    load();
                  }}
                />
              )}
              {canDisconnect && (
                <Button
                  variant="danger"
                  onClick={async () => {
                    await api.disconnectSlack(ws);
                    load();
                  }}
                >
                  Disconnect
                </Button>
              )}
            </div>
          )
        }
      >
        {slack === undefined ? (
          <Spinner label="Loading Slack integration" />
        ) : slack === null ? (
          <EmptyState
            title="Slack not connected"
            description="Connect a Slack workspace to enable Slack-triggered actions."
          />
        ) : (
          <dl className="divide-y divide-[var(--border)]">
            <Row label="Status">
              <Badge
                tone={slack.status === "CONNECTED" ? "success" : "danger"}
              >
                {slack.status}
              </Badge>
            </Row>
            <Row label="Display name" value={slack.display_name} />
            <Row label="Team ID" value={slack.team_id ?? "—"} />
            <Row label="Token hint" value={slack.credential_hint ?? "—"} />
            <Row
              label="Connected"
              value={new Date(slack.connected_at).toLocaleString()}
            />
            <Row
              label="Last tested"
              value={
                slack.last_tested_at
                  ? new Date(slack.last_tested_at).toLocaleString()
                  : "Never"
              }
            />
            {slack.last_error && (
              <Row label="Last error" value={slack.last_error} />
            )}
          </dl>
        )}
      </Card>

      <ConnectModal
        open={showConnect}
        onClose={() => setShowConnect(false)}
        onConnected={load}
      />
    </div>
  );
}

function Row({ label, value, children }: { label: string; value?: React.ReactNode; children?: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between py-2.5">
      <dt className="text-sm text-[var(--muted)]">{label}</dt>
      <dd className="font-mono text-xs">{children ?? value ?? "—"}</dd>
    </div>
  );
}

function TestButton({ onResult }: { onResult: (r: SlackTestResult) => void }) {
  const ws = getActiveWorkspaceId();
  const [testing, setTesting] = useState(false);

  async function test() {
    setTesting(true);
    try {
      const result = await api.testSlack(ws);
      onResult(result);
    } catch {
      onResult({ ok: false, error: "Test failed" });
    } finally {
      setTesting(false);
    }
  }

  return (
    <Button variant="secondary" onClick={test} loading={testing}>
      Test connection
    </Button>
  );
}

function ConnectModal({
  open,
  onClose,
  onConnected,
}: {
  open: boolean;
  onClose: () => void;
  onConnected: () => void;
}) {
  const ws = getActiveWorkspaceId();
  const [botToken, setBotToken] = useState("");
  const [teamId, setTeamId] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  async function connect() {
    setError("");
    setSaving(true);
    try {
      const data: SlackConnectRequest = {
        bot_token: botToken,
        team_id: teamId.trim(),
        display_name: displayName.trim(),
      };
      await api.connectSlack(data, ws);
      setBotToken("");
      setTeamId("");
      setDisplayName("");
      onConnected();
      onClose();
    } catch (err) {
      const apiError = err as ApiError;
      setError(apiError.message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <Modal open={open} onClose={onClose} title="Connect Slack">
      <div className="space-y-4">
        <ErrorBanner message={error} />
        <Field label="Bot token (xoxb-...)">
          <Input
            type="password"
            value={botToken}
            onChange={(e) => setBotToken(e.target.value)}
            placeholder="xoxb-..."
            autoComplete="off"
          />
        </Field>
        <Field label="Team ID">
          <Input
            value={teamId}
            onChange={(e) => setTeamId(e.target.value)}
            placeholder="T01234567"
          />
        </Field>
        <Field label="Display name">
          <Input
            value={displayName}
            onChange={(e) => setDisplayName(e.target.value)}
            placeholder="My Slack workspace"
          />
        </Field>
        <p className="text-xs text-[var(--muted)]">
          The bot token is encrypted at rest. Only a masked hint is ever displayed.
        </p>
        <div className="flex justify-end gap-2">
          <Button variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button
            onClick={connect}
            loading={saving}
            disabled={!botToken || !teamId.trim() || !displayName.trim()}
          >
            Connect
          </Button>
        </div>
      </div>
    </Modal>
  );
}
