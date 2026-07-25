import { NextResponse, type NextRequest } from "next/server";
import { getToken, COOKIE_NAME } from "@/lib/auth";

/**
 * Server-side page protection.
 *
 * The dashboard pages (under /rules, /intents, /blacklist, /test) MUST be
 * gated on the server so that even a non-JS client (e.g. curl) is redirected
 * to /login rather than receiving the page HTML. The page's client-side
 * `useEffect` redirect is only a secondary safeguard for the cookie-less case.
 *
 * API routes (/api/*) and the login page itself are NOT gated here — they do
 * their own auth (APIs call authorize(); /login must obviously be reachable
 * without a cookie). Static assets are left to Next's default handling.
 */
const PROTECTED_PREFIXES = ["/rules", "/intents", "/blacklist", "/test"];

export function middleware(req: NextRequest) {
  const { pathname } = req.nextUrl;

  const isProtected = PROTECTED_PREFIXES.some(
    (p) => pathname === p || pathname.startsWith(p + "/")
  );
  if (!isProtected) {
    return NextResponse.next();
  }

  let expected: string;
  try {
    expected = getToken();
  } catch {
    // Server misconfigured — return 500 so the operator notices immediately.
    return NextResponse.json(
      { error: "server misconfigured: missing AUTORERANKER_TOKEN" },
      { status: 500 }
    );
  }

  const cookieToken = req.cookies.get(COOKIE_NAME)?.value;
  const header = req.headers.get("authorization") || "";
  const headerToken = header.toLowerCase().startsWith("bearer ")
    ? header.slice(7).trim()
    : null;
  const provided = cookieToken || headerToken;

  if (!provided || provided !== expected) {
    // For HTML page requests, redirect to login. For non-HTML (e.g. JSON
    // probes from curl), return 401 so the caller isn't confused by HTML.
    const accept = req.headers.get("accept") || "";
    if (accept.includes("text/html")) {
      const loginUrl = req.nextUrl.clone();
      loginUrl.pathname = "/login";
      return NextResponse.redirect(loginUrl);
    }
    return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  }

  return NextResponse.next();
}

export const config = {
  // Run on all paths except API routes, the login page, and Next internals.
  // (We could be more permissive, but matcher runs BEFORE the function body,
  // and narrowing here reduces overhead on unrelated paths.)
  matcher: ["/((?!api|login|_next/static|_next/image|favicon.ico).*)"],
};
