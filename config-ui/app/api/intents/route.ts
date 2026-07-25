import { NextRequest } from "next/server";
import { authorize, fromWebRequest } from "@/lib/auth";
import { authResponse } from "@/lib/auth_adapter";
import { withClient } from "@/lib/db";
import { ok, bad, serverError } from "@/lib/http";
import { validateNonEmpty } from "@/lib/validation";

/** GET /api/intents */
export async function GET(req: NextRequest) {
  const auth = authorize(fromWebRequest(req));
  const denied = authResponse(auth);
  if (denied) return denied;
  try {
    const rows = await withClient(async (c) => {
      const { rows } = await c.query(
        `SELECT i.id, i.name, i.description, i.priority, i.enabled,
                i.created_at, i.updated_at,
                COALESCE(
                  (SELECT json_agg(json_build_object('id', k.id, 'keyword', k.keyword))
                     FROM intent_keywords k WHERE k.intent_id = i.id),
                  '[]'::json
                ) AS keywords
           FROM intents i
          ORDER BY i.priority ASC, i.id ASC`
      );
      return rows;
    });
    return ok(rows);
  } catch (e) {
    return serverError((e as Error).message);
  }
}

/** POST /api/intents  body: { name, description?, priority?, enabled? } */
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

  const nameErr = validateNonEmpty("name", body.name);
  if (nameErr) return bad(nameErr.message, nameErr);

  const priority = Number(body.priority ?? 100);
  if (!Number.isInteger(priority)) return bad("priority must be an integer");

  try {
    const rows = await withClient(async (c) => {
      const { rows } = await c.query(
        `INSERT INTO intents (name, description, priority, enabled)
         VALUES ($1, $2, $3, $4)
         RETURNING id, name, description, priority, enabled, created_at, updated_at`,
        [body.name, body.description ?? null, priority, body.enabled !== false]
      );
      return rows;
    });
    return ok(rows[0], 201);
  } catch (e) {
    return serverError((e as Error).message);
  }
}
