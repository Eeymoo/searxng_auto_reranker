import { NextRequest } from "next/server";
import { cookies } from "next/headers";
import { ok, bad, serverError } from "@/lib/http";
import { getToken, COOKIE_NAME } from "@/lib/auth";

/**
 * POST /api/login  body: { token: string }
 *
 * Validates the provided token against AUTORERANKER_TOKEN and, on match, sets
 * an HttpOnly cookie so subsequent requests (pages + APIs) are authenticated
 * without the JS layer needing to read the token. The cookie is the primary
 * auth path; it is not visible to client-side JS (XSS-resistant).
 */
export async function POST(req: NextRequest) {
  let body: Record<string, unknown>;
  try {
    body = await req.json();
  } catch {
    return bad("invalid JSON body");
  }

  const provided = typeof body.token === "string" ? body.token : "";
  if (!provided) return bad("token is required");

  let expected: string;
  try {
    expected = getToken();
  } catch {
    return serverError("server misconfigured: missing AUTORERANKER_TOKEN");
  }

  if (provided !== expected) {
    return bad("invalid token");
  }

  // Set the HttpOnly cookie. SameSite=Strict defends against CSRF; Secure is
  // added only in production (behind TLS) so local dev over http still works.
  const isProduction = process.env.NODE_ENV === "production";
  cookies().set({
    name: COOKIE_NAME,
    value: provided,
    httpOnly: true,
    sameSite: "strict",
    secure: isProduction,
    path: "/",
    // 7-day expiry; the token itself is the real credential so a rolling
    // expiry just avoids leaving stale cookies on shared machines.
    maxAge: 60 * 60 * 24 * 7,
  });

  return ok({ ok: true });
}
