/**
 * Thin browser-side client for the config-ui API.
 *
 * Authentication is primarily via an HttpOnly cookie set by the login server
 * action; the browser auto-attaches it to same-origin requests. We do NOT read
 * the token in JS (HttpOnly prevents that, by design — defeats XSS theft).
 *
 * The localStorage helpers below are kept only so programmatic clients (e.g.
 * a curl shell that prefers bearer headers) can still pass a token via the
 * `Authorization` header — they are no longer used by the web UI itself.
 */

const TOKEN_KEY = "auto_reranker_token";

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string): void {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(TOKEN_KEY, token);
}

export function clearToken(): void {
  if (typeof window === "undefined") return;
  window.localStorage.removeItem(TOKEN_KEY);
}

export class ApiError extends Error {
  constructor(public status: number, message: string, public details?: unknown) {
    super(message);
  }
}

async function request<T>(
  path: string,
  init: RequestInit = {}
): Promise<T> {
  const headers = new Headers(init.headers);
  headers.set("Content-Type", "application/json");
  const token = getToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);

  const resp = await fetch(path, { ...init, headers });
  const text = await resp.text();
  const body = text ? JSON.parse(text) : null;
  if (!resp.ok) {
    throw new ApiError(
      resp.status,
      body?.error || `request failed: ${resp.status}`,
      body?.details
    );
  }
  return body as T;
}

export const api = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: "POST", body: body ? JSON.stringify(body) : undefined }),
  patch: <T>(path: string, body: unknown) =>
    request<T>(path, { method: "PATCH", body: JSON.stringify(body) }),
  delete: <T>(path: string) => request<T>(path, { method: "DELETE" }),
};

// ----------------------------------------------------------------- //
// typed models
// ----------------------------------------------------------------- //
export interface Rule {
  id: number;
  pattern: string;
  coefficient: number;
  priority: number;
  intent_id: number | null;
  enabled: boolean;
  description: string | null;
  created_at: string;
  updated_at: string;
}

export interface Intent {
  id: number;
  name: string;
  description: string | null;
  priority: number;
  enabled: boolean;
  created_at: string;
  updated_at: string;
  keywords: { id: number; keyword: string }[];
}

export interface TestResult {
  url: string;
  query: string;
  matched_rule: {
    id: number;
    pattern: string;
    coefficient: number;
    priority: number;
    intent_id: number | null;
    description: string | null;
  } | null;
  coefficient: number;
  dropped: boolean;
  evaluated_rule_count: number;
}
