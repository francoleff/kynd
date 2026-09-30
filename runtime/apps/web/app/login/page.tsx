"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useState } from "react";

import { Button, ErrorBanner, Field, Input } from "@/components/ui";
import { ApiError, api } from "@/lib/api";
import { setActiveWorkspaceId } from "@/lib/session";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [errorId, setErrorId] = useState<string | undefined>();
  const [loading, setLoading] = useState(false);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setError("");
    setErrorId(undefined);
    setLoading(true);
    try {
      const result = await api.login({ email, password });
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
      <h1 className="mt-4 text-2xl font-semibold">Sign in</h1>

      <form onSubmit={onSubmit} className="mt-8 space-y-4" noValidate>
        <ErrorBanner message={error} errorId={errorId} />

        <Field label="Email">
          <Input
            type="email"
            required
            autoComplete="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
        </Field>

        <Field label="Password">
          <Input
            type="password"
            required
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </Field>

        <Button type="submit" loading={loading} className="w-full">
          Sign in
        </Button>
      </form>

      <p className="mt-6 text-sm text-[var(--muted)]">
        No account?{" "}
        <Link href="/signup" className="text-[var(--foreground)] underline">
          Create one
        </Link>
      </p>
    </main>
  );
}
