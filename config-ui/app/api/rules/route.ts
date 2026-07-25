import { NextRequest } from "next/server";
import { authorize, fromWebRequest } from "@/lib/auth";
import { authResponse } from "@/lib/auth_adapter";
import { withClient } from "@/lib/db";
import { ok, bad, serverError } from "@/lib/http";
import { validateCoefficient, validatePattern } from "@/lib/validation";

/** GET /api/rules?intent_id=&generic=1&blacklist=1 */
export async function GET(req: NextRequest) {
  const auth = authorize(fromWebRequest(req));
  const denied = authResponse(auth);
  if (denied) return denied;

  const url = new URL(req.url);
  const intentId = url.searchParams.get("intent_id");
  const genericOnly = url.searchParams.get("generic") === "1";
  const blacklistOnly = url.searchParams.get("blacklist") === "1";

  try {
    const rows = await withClient(async (c) => {
      const conditions: string[] = [];
      const params: unknown[] = [];
      if (blacklistOnly) {
        conditions.push("coefficient = 0");
      }
      if (genericOnly) {
        conditions.push("intent_id IS NULL");
      }
      if (intentId !== null) {
        params.push(Number(intentId));
        conditions.push("intent_id = $" + params.length);
      }
      const where = conditions.length ? "WHERE " + conditions.join(" AND ") : "";
      const { rows } = await c.query(
        `SELECT id, pattern, coefficient, priority, intent_id, enabled, description,
                created_at, updated_at
           FROM rules ${where}
          ORDER BY priority ASC, id ASC`,
        params
      );
      return rows;
    });
    return ok(rows);
  } catch (e) {
    return serverError((e as Error).message);
  }
}

/** POST /api/rules  body: { pattern, coefficient, priority?, intent_id?, enabled?, description? } */
export async function POST(req: NextRequest) {
  const auth = authorize(fromWebRequest(req));
  const denied = authResponse(auth);
  if (denied) return denied;

  let body: Record<string, unknown>;
  try {
    body = await req.json();
  } catch {
    return bad("invalid JSON body");
  }

  const patternErr = validatePattern(body.pattern);
  if (patternErr) return bad(patternErr.message, patternErr);

  const coeffErr = validateCoefficient(body.coefficient);
  if (coeffErr) return bad(coeffErr.message, coeffErr);

  const priority = Number(body.priority ?? 100);
  if (!Number.isInteger(priority)) return bad("priority must be an integer");

  const intentId =
    body.intent_id === null || body.intent_id === undefined
      ? null
      : Number(body.intent_id);
  if (intentId !== null && !Number.isInteger(intentId)) {
    return bad("intent_id must be an integer or null");
  }

  try {
    const rows = await withClient(async (c) => {
      const { rows } = await c.query(
        `INSERT INTO rules (pattern, coefficient, priority, intent_id, enabled, description)
         VALUES ($1, $2, $3, $4, $5, $6)
         RETURNING id, pattern, coefficient, priority, intent_id, enabled, description,
                   created_at, updated_at`,
        [
          body.pattern,
          body.coefficient,
          priority,
          intentId,
          body.enabled !== false,
          body.description ?? null,
        ]
      );
      return rows;
    });
    return ok(rows[0], 201);
  } catch (e) {
    return serverError((e as Error).message);
  }
}
