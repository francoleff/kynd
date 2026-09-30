/**
 * API client.
 *
 * Every call sends the session cookie (`credentials: "include"`), which is why
 * the API's CORS config sets an explicit origin rather than "*" — the two are
 * only valid together.
 *
 * The session cookie is httpOnly, so this module cannot read it. That is the
 * point: an XSS payload on this page cannot steal the session either.
 */

export const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

export class ApiError extends Error {
  status: number;
  errorId?: string;

  constructor(message: string, status: number, errorId?: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.errorId = errorId;
  }
}

async function request<T>(
  path: string,
  options: RequestInit = {},
  workspaceId?: string,
): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...((options.headers as Record<string, string>) ?? {}),
  };
  if (workspaceId) headers["X-Kynd-Workspace"] = workspaceId;

  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      ...options,
      headers,
      credentials: "include",
      cache: "no-store",
    });
  } catch {
    // A network-level failure, not an API response. Say so plainly rather
    // than rendering "undefined".
    throw new ApiError("Could not reach the Kynd API. Is it running?", 0);
  }

  if (response.status === 204) return undefined as T;

  const text = await response.text();
  let body: unknown = null;
  try {
    body = text ? JSON.parse(text) : null;
  } catch {
    body = null;
  }

  if (!response.ok) {
    const record = (body ?? {}) as Record<string, unknown>;
    let detail = record.detail ?? "Request failed";
    // FastAPI validation errors arrive as an array of objects; rendering that
    // raw puts "[object Object]" in front of a customer.
    if (Array.isArray(detail)) {
      detail = detail
        .map((item) => (item as Record<string, unknown>)?.msg ?? "Invalid input")
        .join(", ");
    }
    throw new ApiError(
      String(detail),
      response.status,
      record.error_id as string | undefined,
    );
  }

  return body as T;
}

export type Role = "OWNER" | "ADMIN" | "OPERATOR" | "VIEWER";

export interface User {
  id: string;
  email: string;
  name: string | null;
  email_verified: boolean;
  created_at: string;
}

export interface Workspace {
  id: string;
  name: string;
  slug: string;
  onboarding_completed: boolean;
  created_at: string;
}

export interface WorkspaceSummary {
  id: string;
  name: string;
  slug: string;
  role: Role;
}

export interface MeResponse {
  user: User;
  workspaces: WorkspaceSummary[];
  current_workspace: Workspace | null;
  role: Role | null;
  permissions: string[];
}

export interface AuthResponse {
  user: User;
  workspace: Workspace;
  role: Role;
}

export interface Member {
  id: string;
  user_id: string;
  workspace_id: string;
  role: Role;
  email: string;
  name: string | null;
  created_at: string;
}

// ---------------------------------------------------------------------------
// Governance: capabilities
// ---------------------------------------------------------------------------

export interface WorkspaceCapabilityOut {
  id: string;
  workspace_id: string;
  integration_id: string | null;
  name: string;
  enabled: boolean;
  max_amount: number | null;
  max_calls_per_day: number | null;
  allowed_targets: string[] | null;
  requires_approval: boolean;
  created_at: string;
  updated_at: string;
}

export interface WorkspaceCapabilityCreate {
  name: string;
  enabled?: boolean;
  max_amount?: number | null;
  max_calls_per_day?: number | null;
  allowed_targets?: string[] | null;
  requires_approval?: boolean;
}

export interface WorkspaceCapabilityUpdate {
  enabled?: boolean | null;
  max_amount?: number | null;
  max_calls_per_day?: number | null;
  allowed_targets?: string[] | null;
  requires_approval?: boolean | null;
}

// ---------------------------------------------------------------------------
// Governance: rules
// ---------------------------------------------------------------------------

export interface GovernanceRuleOut {
  id: string;
  workspace_id: string;
  name: string;
  rule_type: string;
  config: Record<string, unknown>;
  enabled: boolean;
  created_at: string;
  updated_at: string;
}

export interface GovernanceRuleCreate {
  name: string;
  rule_type: string;
  config?: Record<string, unknown>;
  enabled?: boolean;
}

export interface GovernanceRuleUpdate {
  name?: string | null;
  config?: Record<string, unknown> | null;
  enabled?: boolean | null;
}

// ---------------------------------------------------------------------------
// Governance: preview + simulate
// ---------------------------------------------------------------------------

export interface GovernancePreview {
  allowed: string[];
  blocked_capabilities: string[];
  blocked_action_types: string[];
  approval_required: string[];
  limits: Record<string, Record<string, unknown>>;
}

export interface SimulateRequest {
  type: string;
  capability: string;
  params?: Record<string, unknown>;
  amount?: number | null;
}

export interface SimulateResponse {
  allowed: boolean;
  reason: string;
}

// ---------------------------------------------------------------------------
// Approvals
// ---------------------------------------------------------------------------

export interface ApprovalRequestOut {
  id: string;
  workspace_id: string;
  capability: string;
  action_type: string | null;
  target: string | null;
  amount: number | null;
  params: Record<string, unknown>;
  reason: string | null;
  status: string;
  requested_by_user_id: string | null;
  decided_by_user_id: string | null;
  decided_at: string | null;
  decision_note: string | null;
  expires_at: string;
  created_at: string;
}

export interface ApprovalRequestCreate {
  capability: string;
  action_type?: string | null;
  target?: string | null;
  amount?: number | null;
  params?: Record<string, unknown>;
  reason?: string | null;
}

export interface ApprovalDecisionRequest {
  note?: string | null;
}

// ---------------------------------------------------------------------------
// Executions
// ---------------------------------------------------------------------------

export interface ExecutionRecordOut {
  id: number;
  ts: number;
  capability: string;
  action_type: string | null;
  outcome: string;
  reason: string;
  idempotency_key: string | null;
  error: string | null;
}

// ---------------------------------------------------------------------------
// Audit
// ---------------------------------------------------------------------------

export interface AuditEventOut {
  id: string;
  workspace_id: string;
  event_type: string;
  outcome: string;
  actor_user_id: string | null;
  resource_type: string;
  resource_id: string | null;
  metadata: Record<string, unknown>;
  runtime_execution_id: number | null;
  approval_request_id: string | null;
  created_at: string;
}

// ---------------------------------------------------------------------------
// Proposals
// ---------------------------------------------------------------------------

export interface AIProposalOut {
  id: string;
  workspace_id: string;
  intent: string;
  capability: string | null;
  action_type: string | null;
  target: string | null;
  amount: number | null;
  params: Record<string, unknown>;
  status: string;
  rejection_reason: string | null;
  approval_request_id: string | null;
  created_by_user_id: string | null;
  created_at: string;
}

export interface ProposalGenerateRequest {
  intent: string;
  hints?: Record<string, unknown>;
}

// ---------------------------------------------------------------------------
// Integrations: Slack
// ---------------------------------------------------------------------------

export interface SlackIntegrationOut {
  id: string;
  workspace_id: string;
  status: string;
  display_name: string;
  team_id: string | null;
  credential_hint: string | null;
  connected_at: string;
  last_tested_at: string | null;
  last_error: string | null;
}

export interface SlackConnectRequest {
  bot_token: string;
  team_id: string;
  display_name: string;
}

export interface SlackTestResult {
  ok: boolean;
  error: string | null;
}

// ---------------------------------------------------------------------------
// API methods
// ---------------------------------------------------------------------------

export const api = {
  signup: (data: {
    email: string;
    password: string;
    workspace_name: string;
    name?: string;
  }) =>
    request<AuthResponse>("/auth/signup", {
      method: "POST",
      body: JSON.stringify(data),
    }),

  login: (data: { email: string; password: string }) =>
    request<AuthResponse>("/auth/login", {
      method: "POST",
      body: JSON.stringify(data),
    }),

  logout: () => request<{ message: string }>("/auth/logout", { method: "POST" }),

  me: (workspaceId?: string) => request<MeResponse>("/auth/me", {}, workspaceId),

  workspace: (workspaceId?: string) =>
    request<Workspace>("/workspace", {}, workspaceId),

  members: (workspaceId?: string) =>
    request<Member[]>("/workspace/members", {}, workspaceId),

  // --- Governance: capabilities ---

  listCapabilities: (workspaceId?: string) =>
    request<WorkspaceCapabilityOut[]>("/governance/capabilities", {}, workspaceId),

  createCapability: (data: WorkspaceCapabilityCreate, workspaceId?: string) =>
    request<WorkspaceCapabilityOut>(
      "/governance/capabilities",
      { method: "POST", body: JSON.stringify(data) },
      workspaceId,
    ),

  updateCapability: (
    capabilityId: string,
    data: WorkspaceCapabilityUpdate,
    workspaceId?: string,
  ) =>
    request<WorkspaceCapabilityOut>(
      `/governance/capabilities/${capabilityId}`,
      { method: "PATCH", body: JSON.stringify(data) },
      workspaceId,
    ),

  deleteCapability: (capabilityId: string, workspaceId?: string) =>
    request<{ message: string }>(
      `/governance/capabilities/${capabilityId}`,
      { method: "DELETE" },
      workspaceId,
    ),

  // --- Governance: rules ---

  listRules: (workspaceId?: string) =>
    request<GovernanceRuleOut[]>("/governance/rules", {}, workspaceId),

  createRule: (data: GovernanceRuleCreate, workspaceId?: string) =>
    request<GovernanceRuleOut>(
      "/governance/rules",
      { method: "POST", body: JSON.stringify(data) },
      workspaceId,
    ),

  updateRule: (
    ruleId: string,
    data: GovernanceRuleUpdate,
    workspaceId?: string,
  ) =>
    request<GovernanceRuleOut>(
      `/governance/rules/${ruleId}`,
      { method: "PATCH", body: JSON.stringify(data) },
      workspaceId,
    ),

  deleteRule: (ruleId: string, workspaceId?: string) =>
    request<{ message: string }>(
      `/governance/rules/${ruleId}`,
      { method: "DELETE" },
      workspaceId,
    ),

  // --- Governance: preview + simulate ---

  previewConstitution: (workspaceId?: string) =>
    request<GovernancePreview>("/governance/preview", {}, workspaceId),

  simulateAction: (data: SimulateRequest, workspaceId?: string) =>
    request<SimulateResponse>(
      "/governance/simulate",
      { method: "POST", body: JSON.stringify(data) },
      workspaceId,
    ),

  // --- Approvals ---

  createApproval: (data: ApprovalRequestCreate, workspaceId?: string) =>
    request<ApprovalRequestOut>(
      "/approvals",
      { method: "POST", body: JSON.stringify(data) },
      workspaceId,
    ),

  listApprovals: (status?: string, workspaceId?: string) =>
    request<ApprovalRequestOut[]>(
      `/approvals${status ? `?status=${encodeURIComponent(status)}` : ""}`,
      {},
      workspaceId,
    ),

  getApproval: (requestId: string, workspaceId?: string) =>
    request<ApprovalRequestOut>(`/approvals/${requestId}`, {}, workspaceId),

  approveRequest: (
    requestId: string,
    data?: ApprovalDecisionRequest,
    workspaceId?: string,
  ) =>
    request<ApprovalRequestOut>(
      `/approvals/${requestId}/approve`,
      { method: "POST", body: JSON.stringify(data ?? {}) },
      workspaceId,
    ),

  rejectRequest: (
    requestId: string,
    data?: ApprovalDecisionRequest,
    workspaceId?: string,
  ) =>
    request<ApprovalRequestOut>(
      `/approvals/${requestId}/reject`,
      { method: "POST", body: JSON.stringify(data ?? {}) },
      workspaceId,
    ),

  // --- Executions ---

  listExecutions: (workspaceId?: string) =>
    request<ExecutionRecordOut[]>("/executions", {}, workspaceId),

  getExecution: (executionId: number, workspaceId?: string) =>
    request<ExecutionRecordOut>(`/executions/${executionId}`, {}, workspaceId),

  // --- Audit ---

  listAuditEvents: (workspaceId?: string) =>
    request<AuditEventOut[]>("/audit", {}, workspaceId),

  getAuditEvent: (eventId: string, workspaceId?: string) =>
    request<AuditEventOut>(`/audit/${eventId}`, {}, workspaceId),

  // --- Proposals ---

  generateProposal: (data: ProposalGenerateRequest, workspaceId?: string) =>
    request<AIProposalOut>(
      "/proposals/generate",
      { method: "POST", body: JSON.stringify(data) },
      workspaceId,
    ),

  listProposals: (workspaceId?: string) =>
    request<AIProposalOut[]>("/proposals", {}, workspaceId),

  getProposal: (proposalId: string, workspaceId?: string) =>
    request<AIProposalOut>(`/proposals/${proposalId}`, {}, workspaceId),

  // --- Integrations: Slack ---

  getSlackIntegration: (workspaceId?: string) =>
    request<SlackIntegrationOut | null>("/integrations/slack", {}, workspaceId),

  connectSlack: (data: SlackConnectRequest, workspaceId?: string) =>
    request<SlackIntegrationOut>(
      "/integrations/slack/connect",
      { method: "POST", body: JSON.stringify(data) },
      workspaceId,
    ),

  disconnectSlack: (workspaceId?: string) =>
    request<SlackIntegrationOut>(
      "/integrations/slack/disconnect",
      { method: "POST" },
      workspaceId,
    ),

  testSlack: (workspaceId?: string) =>
    request<SlackTestResult>(
      "/integrations/slack/test",
      { method: "POST" },
      workspaceId,
    ),
};
