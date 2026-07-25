import { NextResponse } from "next/server";
import type { AuthResult } from "./auth";

/** Convert an AuthResult into a NextResponse (no-op for ok). */
export function authResponse(r: AuthResult): NextResponse | null {
  if (r.ok) return null;
  return NextResponse.json(r.body, { status: r.status });
}
