import Link from "next/link";

export default function Home() {
  return (
    <main className="mx-auto flex min-h-screen max-w-3xl flex-col justify-center px-6 py-16">
      <p className="font-mono text-xs uppercase tracking-widest text-[var(--accent)]">
        Kynd OS
      </p>
      <h1 className="mt-4 text-4xl font-semibold leading-tight sm:text-5xl">
        AI proposes.
        <br />
        Kynd decides.
      </h1>
      <p className="mt-5 max-w-xl text-[var(--muted)]">
        Control, approve, execute, and audit every AI and automation action
        through deterministic governance. Not a prompt asking a model to behave
        — code that stops it.
      </p>

      <div className="mt-8 flex gap-3">
        <Link
          href="/signup"
          className="rounded-md bg-[var(--accent)] px-5 py-2.5 text-sm font-medium text-white transition-colors hover:bg-[var(--accent-hover)]"
        >
          Create an account
        </Link>
        <Link
          href="/login"
          className="rounded-md border border-[var(--border)] px-5 py-2.5 text-sm font-medium transition-colors hover:border-[var(--muted)]"
        >
          Sign in
        </Link>
      </div>

      <div className="mt-14 grid gap-3 sm:grid-cols-3">
        {[
          ["Deterministic", "Rules are code, not prompts. The model cannot argue with them."],
          ["Human approval", "Actions that need a person wait for a person."],
          ["Fully audited", "Every decision, allowed or blocked, is recorded."],
        ].map(([title, body]) => (
          <div
            key={title}
            className="rounded-lg border border-[var(--border)] bg-[var(--surface)] p-4"
          >
            <p className="text-sm font-medium">{title}</p>
            <p className="mt-1 text-sm text-[var(--muted)]">{body}</p>
          </div>
        ))}
      </div>
    </main>
  );
}
