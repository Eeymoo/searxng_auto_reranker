import { NextRequest } from "next/server";
import { authorize, fromWebRequest } from "@/lib/auth";
import { authResponse } from "@/lib/auth_adapter";
import { withClient } from "@/lib/db";
import { ok, bad, serverError } from "@/lib/http";
import { validatePattern } from "@/lib/validation";

/**
 * Blacklist endpoints. The blacklist is stored as `rules` with coefficient = 0;
 * these routes are a filtered projection over that table so the UI can present
 * them in a dedicated view.
 */

/** GET /api/blacklist  -> rules where coefficient = 0 */
export async function GET(req: NextRequest) {
  const auth = authorize(fromWebRequest(req));
  const denied = authResponse(auth);
  if (denied) return denied;
  try {
    const rows = await withClient(async (c) => {
      const { rows } = await c.query(
        `SELECT id, pattern, priority, intent_id, enabled, description,
                created_at, updated_at
           FROM rules
          WHERE coefficient = 0
          ORDER BY priority ASC, id ASC`
      );
      return rows;
    });
    return ok(rows);
  } catch (e) {
    return serverError((e as Error).message);
  }
}

/** POST /api/blacklist  body: { pattern, priority?, intent_id?, description? }
 *  -> creates a rule with coefficient = 0 */
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
  const err = validatePattern(body.pattern);
  if (err) return bad(err.message, err);

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
         VALUES ($1, 0, $2, $3, TRUE, $4)
         RETURNING id, pattern, coefficient, priority, intent_id, enabled, description,
                   created_at, updated_at`,
        [body.pattern, priority, intentId, body.description ?? null]
      );
      return rows;
    });
    return ok(rows[0], 201);
  } catch (e) {
    return serverError((e as Error).message);
  }
}
