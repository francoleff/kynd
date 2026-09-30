"use client";

/**
 * Workspace context.
 *
 * The dashboard layout fetches `/auth/me` once and shares it. Before this,
 * the layout and each page fetched independently, which meant two round trips
 * per navigation and — visibly — a rendered header sitting above a second
 * "Loading" spinner. Caught by screenshotting the real browser; the text
 * assertions passed because the header alone contained the expected strings.
 */

import { createContext, useContext } from "react";

import { MeResponse } from "@/lib/api";

export interface WorkspaceContextValue {
  me: MeResponse;
  refresh: () => Promise<void>;
}

const WorkspaceContext = createContext<WorkspaceContextValue | null>(null);

export const WorkspaceProvider = WorkspaceContext.Provider;

export function useWorkspace(): WorkspaceContextValue {
  const value = useContext(WorkspaceContext);
  if (!value) {
    // A hard error rather than a silent undefined: a page rendering outside the
    // provider would otherwise fail later with a confusing null dereference.
    throw new Error("useWorkspace must be used inside the dashboard layout");
  }
  return value;
}

/** Whether the current role holds a permission. The API enforces the same list. */
export function useCan(permission: string): boolean {
  const { me } = useWorkspace();
  return me.permissions.includes(permission);
}
