"use client";

import { ReactNode } from "react";

export function Button({
  children,
  variant = "primary",
  loading = false,
  className = "",
  ...props
}: {
  children: ReactNode;
  variant?: "primary" | "secondary" | "danger" | "ghost";
  loading?: boolean;
} & React.ButtonHTMLAttributes<HTMLButtonElement>) {
  const base =
    "inline-flex items-center justify-center gap-2 rounded-md px-4 py-2 text-sm font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed";
  const variants = {
    primary: "bg-[var(--accent)] text-white hover:bg-[var(--accent-hover)]",
    secondary:
      "bg-[var(--surface-raised)] text-[var(--foreground)] border border-[var(--border)] hover:border-[var(--muted)]",
    danger: "bg-[var(--danger)] text-white hover:opacity-90",
    ghost: "text-[var(--muted)] hover:text-[var(--foreground)]",
  } as const;

  return (
    <button
      className={`${base} ${variants[variant]} ${className}`}
      disabled={loading || props.disabled}
      {...props}
    >
      {loading && (
        <span
          aria-hidden
          className="h-3 w-3 animate-spin rounded-full border-2 border-current border-t-transparent"
        />
      )}
      {children}
    </button>
  );
}

export function Field({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: ReactNode;
}) {
  return (
    <label className="block space-y-1.5">
      <span className="text-sm font-medium text-[var(--foreground)]">{label}</span>
      {children}
      {hint && <span className="block text-xs text-[var(--muted)]">{hint}</span>}
    </label>
  );
}

export function Input(props: React.InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      {...props}
      className={`w-full rounded-md px-3 py-2 text-sm transition-colors ${props.className ?? ""}`}
    />
  );
}

/** An error the customer can act on. Never a stack trace. */
export function ErrorBanner({
  message,
  errorId,
}: {
  message: string;
  errorId?: string;
}) {
  if (!message) return null;
  return (
    <div
      role="alert"
      className="rounded-md border border-[var(--danger)] bg-[var(--danger)]/10 px-3 py-2 text-sm text-[var(--foreground)]"
    >
      <p>{message}</p>
      {errorId && (
        <p className="mt-1 font-mono text-xs text-[var(--muted)]">
          Reference: {errorId}
        </p>
      )}
    </div>
  );
}

export function Card({
  title,
  description,
  children,
  action,
}: {
  title?: string;
  description?: string;
  children: ReactNode;
  action?: ReactNode;
}) {
  return (
    <section className="rounded-lg border border-[var(--border)] bg-[var(--surface)] p-5">
      {(title || action) && (
        <header className="mb-4 flex items-start justify-between gap-4">
          <div>
            {title && <h2 className="text-base font-semibold">{title}</h2>}
            {description && (
              <p className="mt-0.5 text-sm text-[var(--muted)]">{description}</p>
            )}
          </div>
          {action}
        </header>
      )}
      {children}
    </section>
  );
}

export function Badge({
  children,
  tone = "neutral",
}: {
  children: ReactNode;
  tone?: "neutral" | "success" | "warning" | "danger";
}) {
  const tones = {
    neutral: "bg-[var(--surface-raised)] text-[var(--muted)]",
    success: "bg-[var(--success)]/15 text-[var(--success)]",
    warning: "bg-[var(--warning)]/15 text-[var(--warning)]",
    danger: "bg-[var(--danger)]/15 text-[var(--danger)]",
  } as const;
  return (
    <span
      className={`inline-flex items-center rounded px-2 py-0.5 font-mono text-xs ${tones[tone]}`}
    >
      {children}
    </span>
  );
}

/** An honest empty state: says what is missing and what to do about it. */
export function EmptyState({
  title,
  description,
  action,
}: {
  title: string;
  description: string;
  action?: ReactNode;
}) {
  return (
    <div className="rounded-lg border border-dashed border-[var(--border)] px-6 py-10 text-center">
      <p className="text-sm font-medium">{title}</p>
      <p className="mx-auto mt-1 max-w-md text-sm text-[var(--muted)]">
        {description}
      </p>
      {action && <div className="mt-4 flex justify-center">{action}</div>}
    </div>
  );
}

export function Spinner({ label = "Loading" }: { label?: string }) {
  return (
    <div className="flex items-center gap-2 text-sm text-[var(--muted)]">
      <span
        aria-hidden
        className="h-3 w-3 animate-spin rounded-full border-2 border-current border-t-transparent"
      />
      {label}
    </div>
  );
}
