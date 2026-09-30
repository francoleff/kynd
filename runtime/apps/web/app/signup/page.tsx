"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useState } from "react";

import { Button, ErrorBanner, Field, Input } from "@/components/ui";
import { ApiError, api } from "@/lib/api";
import { setActiveWorkspaceId } from "@/lib/session";

export default function SignupPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const [workspaceName, setWorkspaceName] = useState("");
  const [error, setError] = useState("");
  const [errorId, setErrorId] = useState<string | undefined>();
  const [loading, setLoading] = useState(false);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setError("");
    setErrorId(undefined);
    setLoading(true);
    try {
      const result = await api.signup({
        email,
        password,
        workspace_name: workspaceName,
        name: name || undefined,
      });
      setActiveWorkspaceId(result.workspace.id);
      router.push("/dashboard");
    } catch (err) {
      const apiError = err as ApiError;
      setError(apiError.message);
      setErrorId(apiError.errorId);
      setLoading(false);
    }
  }

  return (
    <main className="mx-auto flex min-h-screen max-w-md flex-col justify-center px-6 py-12">
      <Link
        href="/"
        className="font-mono text-xs uppercase tracking-widest text-[var(--accent)]"
      >
        Kynd OS
      </Link>
      <h1 className="mt-4 text-2xl font-semibold">Create your account</h1>
      <p className="mt-1 text-sm text-[var(--muted)]">
        You will get a workspace where you decide what AI is allowed to do.
      </p>

      <form onSubmit={onSubmit} className="mt-8 space-y-4" noValidate>
        <ErrorBanner message={error} errorId={errorId} />

        <Field label="Work email">
          <Input
            type="email"
            required
            autoComplete="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="you@company.com"
          />
        </Field>

        <Field label="Your name">
          <Input
            type="text"
            autoComplete="name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Optional"
          />
        </Field>

        <Field label="Workspace name">
          <Input
            type="text"
            required
            value={workspaceName}
            onChange={(e) => setWorkspaceName(e.target.value)}
            placeholder="Acme Inc"
          />
        </Field>

        <Field
          label="Password"
          hint="At least 12 characters. Length beats symbols."
        >
          <Input
            type="password"
            required
            minLength={12}
            autoComplete="new-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </Field>

        <Button type="submit" loading={loading} className="w-full">
          Create account
        </Button>
      </form>

      <p className="mt-6 text-sm text-[var(--muted)]">
        Already have an account?{" "}
        <Link href="/login" className="text-[var(--foreground)] underline">
          Sign in
        </Link>
      </p>
    </main>
  );
}
