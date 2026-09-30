import { http, HttpResponse } from "msw";

const API = "http://localhost:8000";

export const handlers = [
  http.post(`${API}/auth/login`, () => {
    return HttpResponse.json(
      {
        user: {
          id: "usr_123",
          email: "test@example.com",
          name: "Test User",
          email_verified: true,
          created_at: "2026-01-01T00:00:00Z",
        },
        workspace: {
          id: "ws_123",
          name: "Test Workspace",
          slug: "test-workspace",
          onboarding_completed: false,
          created_at: "2026-01-01T00:00:00Z",
        },
        role: "OWNER",
      },
      { status: 200 },
    );
  }),

  http.post(`${API}/auth/logout`, () => {
    return HttpResponse.json({ message: "Signed out" });
  }),

  http.get(`${API}/auth/me`, () => {
    return HttpResponse.json({
      user: {
        id: "usr_123",
        email: "test@example.com",
        name: "Test User",
        email_verified: true,
        created_at: "2026-01-01T00:00:00Z",
      },
      workspaces: [
        { id: "ws_123", name: "Test Workspace", slug: "test-workspace", role: "OWNER" },
      ],
      current_workspace: {
        id: "ws_123",
        name: "Test Workspace",
        slug: "test-workspace",
        onboarding_completed: false,
        created_at: "2026-01-01T00:00:00Z",
      },
      role: "OWNER",
      permissions: [
        "workspace:read",
        "member:read",
        "integration:read",
        "governance:read",
        "approval:read",
        "execution:read",
        "audit:read",
        "action:propose",
        "approval:decide",
        "integration:test",
        "workspace:update",
        "member:invite",
        "member:update_role",
        "member:remove",
        "integration:connect",
        "integration:disconnect",
        "governance:update",
      ],
    });
  }),

  http.get(`${API}/governance/capabilities`, () => {
    return HttpResponse.json([
      {
        id: "cap_1",
        workspace_id: "ws_123",
        integration_id: null,
        name: "send_email",
        enabled: true,
        max_amount: 1000,
        max_calls_per_day: 100,
        allowed_targets: null,
        requires_approval: false,
        created_at: "2026-01-01T00:00:00Z",
        updated_at: "2026-01-01T00:00:00Z",
      },
    ]);
  }),

  http.get(`${API}/governance/rules`, () => {
    return HttpResponse.json([
      {
        id: "rule_1",
        workspace_id: "ws_123",
        name: "Block payments",
        rule_type: "block_action_type",
        config: { action_types: ["payment"] },
        enabled: true,
        created_at: "2026-01-01T00:00:00Z",
        updated_at: "2026-01-01T00:00:00Z",
      },
    ]);
  }),

  http.get(`${API}/governance/preview`, () => {
    return HttpResponse.json({
      allowed: ["send_email"],
      blocked_capabilities: [],
      blocked_action_types: ["payment"],
      approval_required: [],
      limits: { send_email: { max_amount: 1000, max_calls_per_day: 100, allowed_targets: null } },
    });
  }),

  http.post(`${API}/governance/simulate`, () => {
    return HttpResponse.json({ allowed: false, reason: "Action type blocked by rule" });
  }),

  http.get(`${API}/approvals`, () => {
    return HttpResponse.json([
      {
        id: "apr_1",
        workspace_id: "ws_123",
        capability: "send_email",
        action_type: "send",
        target: "user@example.com",
        amount: null,
        params: {},
        reason: "Welcome email",
        status: "PENDING",
        requested_by_user_id: "usr_123",
        decided_by_user_id: null,
        decided_at: null,
        decision_note: null,
        expires_at: "2026-01-02T00:00:00Z",
        created_at: "2026-01-01T00:00:00Z",
      },
    ]);
  }),

  http.post(`${API}/approvals/apr_1/approve`, () => {
    return HttpResponse.json({
      id: "apr_1",
      workspace_id: "ws_123",
      capability: "send_email",
      action_type: "send",
      target: "user@example.com",
      amount: null,
      params: {},
      reason: "Welcome email",
      status: "APPROVED",
      requested_by_user_id: "usr_123",
      decided_by_user_id: "usr_123",
      decided_at: "2026-01-01T01:00:00Z",
      decision_note: null,
      expires_at: "2026-01-02T00:00:00Z",
      created_at: "2026-01-01T00:00:00Z",
    });
  }),

  http.get(`${API}/executions`, () => {
    return HttpResponse.json([
      {
        id: 1,
        ts: 1704067200,
        capability: "send_email",
        action_type: "send",
        outcome: "SUCCEEDED",
        reason: "Action allowed",
        idempotency_key: null,
        error: null,
      },
    ]);
  }),

  http.get(`${API}/audit`, () => {
    return HttpResponse.json([
      {
        id: "aud_1",
        workspace_id: "ws_123",
        event_type: "approval.approved",
        outcome: "SUCCESS",
        actor_user_id: "usr_123",
        resource_type: "approval_request",
        resource_id: "apr_1",
        metadata: {},
        runtime_execution_id: null,
        approval_request_id: "apr_1",
        created_at: "2026-01-01T01:00:00Z",
      },
    ]);
  }),

  http.get(`${API}/proposals`, () => {
    return HttpResponse.json([
      {
        id: "prop_1",
        workspace_id: "ws_123",
        intent: "Send welcome email",
        capability: "send_email",
        action_type: "send",
        target: "user@example.com",
        amount: null,
        params: {},
        status: "ROUTED_TO_APPROVAL",
        rejection_reason: null,
        approval_request_id: "apr_1",
        created_by_user_id: "usr_123",
        created_at: "2026-01-01T00:00:00Z",
      },
    ]);
  }),

  http.get(`${API}/integrations/slack`, () => {
    return HttpResponse.json({
      id: "int_1",
      workspace_id: "ws_123",
      status: "CONNECTED",
      display_name: "My Slack",
      team_id: "T123",
      credential_hint: "xoxb-...4f2a",
      connected_at: "2026-01-01T00:00:00Z",
      last_tested_at: null,
      last_error: null,
    });
  }),

  http.post(`${API}/integrations/slack/test`, () => {
    return HttpResponse.json({ ok: true, error: null });
  }),
];
