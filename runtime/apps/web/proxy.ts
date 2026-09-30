import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

/**
 * Proxy (Next.js 16 renamed `middleware.ts` to `proxy.ts`; the API is
 * otherwise unchanged — see node_modules/next/dist/docs/01-app/01-getting-
 * started/16-proxy.md).
 *
 * This is an OPTIMISTIC redirect only: it checks whether a session cookie is
 * PRESENT, not whether it is valid — the cookie is opaque and only the API can
 * verify it. Its job is to avoid flashing a dashboard shell at a signed-out
 * visitor. Real authorization happens on every API call, server-side.
 *
 * The Next.js docs are explicit that proxy must not be used as a full session
 * or authorization solution, and it is not used as one here.
 */
const SESSION_COOKIE = "kynd_session";

export function proxy(request: NextRequest) {
  const hasSession = request.cookies.has(SESSION_COOKIE);
  const { pathname } = request.nextUrl;

  if (!hasSession && pathname.startsWith("/dashboard")) {
    const url = request.nextUrl.clone();
    url.pathname = "/login";
    return NextResponse.redirect(url);
  }

  if (hasSession && (pathname === "/login" || pathname === "/signup")) {
    const url = request.nextUrl.clone();
    url.pathname = "/dashboard";
    return NextResponse.redirect(url);
  }

  return NextResponse.next();
}

export const config = {
  matcher: ["/dashboard/:path*", "/login", "/signup"],
};
