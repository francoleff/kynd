"use client";

/**
 * Which workspace the user is currently looking at.
 *
 * This is a UI *selector* only — it is sent as X-Kynd-Workspace and the server
 * always re-validates it against a real membership. Tampering with this value
 * gets a 404, never another tenant's data. Authority lives on the server.
 */

const KEY = "kynd.workspace_id";

export function getActiveWorkspaceId(): string | undefined {
  if (typeof window === "undefined") return undefined;
  return window.localStorage.getItem(KEY) ?? undefined;
}

export function setActiveWorkspaceId(id: string): void {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(KEY, id);
}

export function clearActiveWorkspaceId(): void {
  if (typeof window === "undefined") return;
  window.localStorage.removeItem(KEY);
}
