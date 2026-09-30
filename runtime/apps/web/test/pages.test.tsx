import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";
import { afterAll, afterEach, beforeAll, describe, expect, it, vi } from "vitest";

import { WorkspaceProvider } from "@/lib/workspace-context";
import { handlers } from "./handlers";

const server = setupServer(...handlers);

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

// Mock next/navigation
const mockPush = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: mockPush, replace: vi.fn() }),
  usePathname: () => "/dashboard",
}));

// Mock session storage
const store: Record<string, string> = {};
vi.mock("@/lib/session", () => ({
  getActiveWorkspaceId: () => "ws_123",
  setActiveWorkspaceId: (id: string) => {
    store.kynd_workspace_id = id;
  },
  clearActiveWorkspaceId: () => {
    delete store.kynd_workspace_id;
  },
}));

const me = {
  user: {
    id: "usr_123",
    email: "test@example.com",
    name: "Test",
    email_verified: true,
    created_at: "",
  },
  workspaces: [],
  current_workspace: {
    id: "ws_123",
    name: "Test Workspace",
    slug: "test",
    onboarding_completed: false,
    created_at: "",
  },
  role: "OWNER" as const,
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
};

function wrap(element: React.ReactNode) {
  return <WorkspaceProvider value={{ me, refresh: vi.fn() }}>{element}</WorkspaceProvider>;
}

describe("LoginPage", () => {
  it("renders sign in form", async () => {
    const { default: LoginPage } = await import("@/app/login/page");
    render(<LoginPage />);
    expect(screen.getByRole("heading", { name: "Sign in" })).toBeInTheDocument();
    expect(screen.getByLabelText("Email")).toBeInTheDocument();
    expect(screen.getByLabelText("Password")).toBeInTheDocument();
  });

  it("shows error on failed login", async () => {
    server.use(
      http.post("http://localhost:8000/auth/login", () => {
        return HttpResponse.json({ detail: "Invalid credentials" }, { status: 401 });
      }),
    );
    const { default: LoginPage } = await import("@/app/login/page");
    render(<LoginPage />);
    await userEvent.type(screen.getByLabelText("Email"), "test@example.com");
    await userEvent.type(screen.getByLabelText("Password"), "wrongpassword");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
    await waitFor(() => {
      expect(screen.getByText("Invalid credentials")).toBeInTheDocument();
    });
  });
});

describe("DashboardPage", () => {
  it("renders workspace name and metrics", async () => {
    const { default: DashboardPage } = await import("@/app/dashboard/page");
    render(wrap(<DashboardPage />));
    expect(screen.getByText("Test Workspace")).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByText("Pending approvals")).toBeInTheDocument();
    });
  });
});

describe("ConstitutionPage", () => {
  it("renders capabilities and rules", async () => {
    const { default: ConstitutionPage } = await import("@/app/dashboard/constitution/page");
    render(wrap(<ConstitutionPage />));
    await waitFor(() => {
      // send_email appears in both the preview card and capabilities table
      expect(screen.getAllByText("send_email").length).toBeGreaterThan(0);
      expect(screen.getByText("Block payments")).toBeInTheDocument();
    });
  });
});

describe("ApprovalsPage", () => {
  it("renders pending approvals", async () => {
    const { default: ApprovalsPage } = await import("@/app/dashboard/approvals/page");
    render(wrap(<ApprovalsPage />));
    await waitFor(() => {
      expect(screen.getByText("PENDING")).toBeInTheDocument();
    });
  });
});

describe("ExecutionsPage", () => {
  it("renders execution history", async () => {
    const { default: ExecutionsPage } = await import("@/app/dashboard/executions/page");
    render(wrap(<ExecutionsPage />));
    await waitFor(() => {
      expect(screen.getAllByText("send_email").length).toBeGreaterThan(0);
      expect(screen.getByText("SUCCEEDED")).toBeInTheDocument();
    });
  });
});

describe("AuditPage", () => {
  it("renders audit events", async () => {
    const { default: AuditPage } = await import("@/app/dashboard/audit/page");
    render(wrap(<AuditPage />));
    await waitFor(() => {
      expect(screen.getByText("approval.approved")).toBeInTheDocument();
    });
  });
});

describe("ProposalsPage", () => {
  it("renders proposals", async () => {
    const { default: ProposalsPage } = await import("@/app/dashboard/proposals/page");
    render(wrap(<ProposalsPage />));
    await waitFor(() => {
      expect(screen.getByText("Send welcome email")).toBeInTheDocument();
      expect(screen.getByText("ROUTED_TO_APPROVAL")).toBeInTheDocument();
    });
  });
});

describe("IntegrationsPage", () => {
  it("renders Slack integration status", async () => {
    const { default: IntegrationsPage } = await import("@/app/dashboard/integrations/page");
    render(wrap(<IntegrationsPage />));
    await waitFor(() => {
      expect(screen.getByText("CONNECTED")).toBeInTheDocument();
      expect(screen.getByText("My Slack")).toBeInTheDocument();
    });
  });
});
