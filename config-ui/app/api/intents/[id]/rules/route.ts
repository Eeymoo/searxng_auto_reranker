import { NextRequest } from "next/server";
import { authorize, fromWebRequest } from "@/lib/auth";
import { authResponse } from "@/lib/auth_adapter";
import { withClient } from "@/lib/db";
import { ok, bad, serverError } from "@/lib/http";
import { validateCoefficient, validatePattern } from "@/lib/validation";

type Ctx = { params: { id: string } };

/** GET /api/intents/:id/rules  -> rules attached to this intent. */
export async function GET(req: NextRequest, ctx: Ctx) {
  const auth = authorize(fromWebRequest(req));
  const denied = authResponse(auth);
  if (denied) return denied;
  const intentId = Number(ctx.params.id);
  if (!Number.isInteger(intentId)) return bad("id must be an integer");
  try {
    const rows = await withClient(async (c) => {
      const { rows } = await c.query(
        `SELECT id, pattern, coefficient, priority, intent_id, enabled, description,
                created_at, updated_at
           FROM rules
          WHERE intent_id = $1
          ORDER BY priority ASC, id ASC`,
        [intentId]
      );
      return rows;
    });
    return ok(rows);
  } catch (e) {
    return serverError((e as Error).message);
  }
}

/**
 * POST /api/intents/:id/rules  body: { pattern, coefficient, priority?, enabled?, description? }
 * Creates a rule scoped to this intent (intent_id is forced to :id).
 * Equivalent to POST /api/rules with intent_id in the body, but follows the
 * REST-nested convention so callers don't repeat the intent id.
 */
export async function POST(req: NextRequest, ctx: Ctx) {
  const auth = authorize(fromWebRequest(req));
  const denied = authResponse(auth);
  if (denied) return denied;
  const intentId = Number(ctx.params.id);
  if (!Number.isInteger(intentId)) return bad("id must be an integer");

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

  try {
    const rows = await withClient(async (c) => {
      // Verify intent exists first so we return a clean 404-style error rather
      // than letting the FK throw a generic server error.
      const intentCheck = await c.query(
        "SELECT 1 FROM intents WHERE id = $1",
        [intentId]
      );
      if (intentCheck.rowCount === 0) {
        return { __notFound: true as const };
      }
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
    if ("__notFound" in rows) {
      return bad(`intent ${intentId} not found`, { intent_id: intentId });
    }
    return ok(rows[0], 201);
  } catch (e) {
    return serverError((e as Error).message);
  }
}
