"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { Spinner } from "@/components/ui";
import { MeResponse, api } from "@/lib/api";
import { clearActiveWorkspaceId, getActiveWorkspaceId, setActiveWorkspaceId } from "@/lib/session";
import { WorkspaceProvider } from "@/lib/workspace-context";

const NAV = [
  { href: "/dashboard", label: "Overview" },
  { href: "/dashboard/constitution", label: "Constitution" },
  { href: "/dashboard/proposals", label: "Proposals" },
  { href: "/dashboard/approvals", label: "Approvals" },
  { href: "/dashboard/executions", label: "Executions" },
  { href: "/dashboard/audit", label: "Audit" },
  { href: "/dashboard/integrations", label: "Integrations" },
  { href: "/dashboard/team", label: "Team" },
];

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const router = useRouter();
  const pathname = usePathname();
  const [me, setMe] = useState<MeResponse | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    const data = await api.me(getActiveWorkspaceId());
    setMe(data);
    if (data.current_workspace) {
      setActiveWorkspaceId(data.current_workspace.id);
    }
    return data;
  }, []);

  useEffect(() => {
    let active = true;
    api
      .me(getActiveWorkspaceId())
      .then((data) => {
        if (!active) return;
        setMe(data);
        if (data.current_workspace) {
          setActiveWorkspaceId(data.current_workspace.id);
        }
        setLoading(false);
      })
      .catch(() => {
        if (!active) return;
        router.replace("/login");
      });
    return () => {
      active = false;
    };
  }, [router]);

  async function signOut() {
    try {
      await api.logout();
    } finally {
      clearActiveWorkspaceId();
      router.push("/login");
    }
  }

  if (loading || !me) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <Spinner label="Loading your workspace" />
      </div>
    );
  }

  return (
    <div className="min-h-screen">
      <header className="border-b border-[var(--border)] bg-[var(--surface)]">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-3">
          <div className="flex items-center gap-6">
            <Link
              href="/dashboard"
              className="font-mono text-xs uppercase tracking-widest text-[var(--accent)]"
            >
              Kynd OS
            </Link>
            <nav className="flex flex-wrap gap-1">
              {NAV.map((item) => {
                const active =
                  pathname === item.href || pathname.startsWith(`${item.href}/`);
                return (
                  <Link
                    key={item.href}
                    href={item.href}
                    className={`rounded-md px-3 py-1.5 text-sm transition-colors ${
                      active
                        ? "bg-[var(--surface-raised)] text-[var(--foreground)]"
                        : "text-[var(--muted)] hover:text-[var(--foreground)]"
                    }`}
                  >
                    {item.label}
                  </Link>
                );
              })}
            </nav>
          </div>

          <div className="flex items-center gap-4">
            <div className="text-right">
              <p className="text-sm leading-tight">
                {me.current_workspace?.name}
              </p>
              <p className="font-mono text-xs leading-tight text-[var(--muted)]">
                {me.user.email} · {me.role}
              </p>
            </div>
            <button
              onClick={signOut}
              className="rounded-md border border-[var(--border)] px-3 py-1.5 text-sm text-[var(--muted)] transition-colors hover:border-[var(--muted)] hover:text-[var(--foreground)]"
            >
              Sign out
            </button>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-6xl px-6 py-8">
        <WorkspaceProvider
          value={{
            me,
            refresh: async () => {
              await load();
            },
          }}
        >
          {children}
        </WorkspaceProvider>
      </main>
    </div>
  );
}
