/**
 * Token authorization for the config UI.
 *
 * The single static bearer token MUST be provided via the AUTORERANKER_TOKEN
 * environment variable. If unset, authentication is impossible and every
 * protected route returns 500.
 *
 * This module is intentionally free of `next/server` imports so it can be
 * unit-tested in plain Node (no Next runtime required). Route handlers wrap
 * the plain objects returned here into NextResponse instances.
 */

export interface AuthInput {
  /** Lower-cased header lookup is performed by the caller. */
  getHeader(name: string): string | null;
  getCookie?(name: string): string | undefined;
}

export interface AuthError {
  ok: false;
  status: number;
  body: { error: string; details?: unknown };
}

export interface AuthOk {
  ok: true;
}

export type AuthResult = AuthOk | AuthError;

export function getToken(): string {
  const token = process.env.AUTORERANKER_TOKEN;
  if (!token) {
    throw new Error(
      "AUTORERANKER_TOKEN environment variable is not set; the config UI cannot authenticate any request."
    );
  }
  return token;
}

/** Name of the HttpOnly auth cookie set on login. */
export const COOKIE_NAME = "auto_reranker_token";

export function authorize(req: AuthInput): AuthResult {
  let expected: string;
  try {
    expected = getToken();
  } catch {
    return {
      ok: false,
      status: 500,
      body: { error: "server misconfigured: missing AUTORERANKER_TOKEN" },
    };
  }

  let provided: string | null = null;
  const header =
    req.getHeader("authorization") || req.getHeader("Authorization");
  if (header && header.toLowerCase().startsWith("bearer ")) {
    provided = header.slice(7).trim();
  }
  if (!provided && typeof req.getCookie === "function") {
    provided = req.getCookie(COOKIE_NAME) ?? null;
  }

  if (!provided || provided !== expected) {
    return { ok: false, status: 401, body: { error: "unauthorized" } };
  }
  return { ok: true };
}

/** Helper: build an AuthInput from a Web Request (used by route handlers). */
export function fromWebRequest(webReq: {
  headers: { get(name: string): string | null };
  cookies: { get(name: string): { value: string } | undefined };
}): AuthInput {
  return {
    getHeader: (name) => webReq.headers.get(name),
    getCookie: (name) => webReq.cookies.get(name)?.value,
  };
}
