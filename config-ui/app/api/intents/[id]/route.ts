import { NextRequest } from "next/server";
import { authorize, fromWebRequest } from "@/lib/auth";
import { authResponse } from "@/lib/auth_adapter";
import { withClient } from "@/lib/db";
import { ok, bad, notFound, serverError } from "@/lib/http";

type Ctx = { params: { id: string } };

export async function GET(req: NextRequest, ctx: Ctx) {
  const auth = authorize(fromWebRequest(req));
  const denied = authResponse(auth);
  if (denied) return denied;
  const id = Number(ctx.params.id);
  if (!Number.isInteger(id)) return bad("id must be an integer");
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
           FROM intents i WHERE i.id = $1`,
        [id]
      );
      return rows;
    });
    if (rows.length === 0) return notFound("intent not found");
    return ok(rows[0]);
  } catch (e) {
    return serverError((e as Error).message);
  }
}

export async function PATCH(req: NextRequest, ctx: Ctx) {
  const auth = authorize(fromWebRequest(req));
  const denied = authResponse(auth);
  if (denied) return denied;
  const id = Number(ctx.params.id);
  if (!Number.isInteger(id)) return bad("id must be an integer");

  let body: Record<string, unknown>;
  try {
    body = await req.json();
  } catch {
    return bad("invalid JSON body");
  }

  const sets: string[] = [];
  const params: unknown[] = [];
  if (body.name !== undefined) {
    if (typeof body.name !== "string" || !body.name.trim()) {
      return bad("name must be non-empty");
    }
    params.push(body.name);
    sets.push(`name = $${params.length}`);
  }
  if (body.description !== undefined) {
    params.push(body.description);
    sets.push(`description = $${params.length}`);
  }
  if (body.priority !== undefined) {
    const p = Number(body.priority);
    if (!Number.isInteger(p)) return bad("priority must be an integer");
    params.push(p);
    sets.push(`priority = $${params.length}`);
  }
  if (body.enabled !== undefined) {
    params.push(Boolean(body.enabled));
    sets.push(`enabled = $${params.length}`);
  }
  if (sets.length === 0) return bad("no fields to update");
  params.push(id);

  try {
    const rows = await withClient(async (c) => {
      const { rows } = await c.query(
        `UPDATE intents SET ${sets.join(", ")} WHERE id = $${params.length}
         RETURNING id, name, description, priority, enabled, created_at, updated_at`,
        params
      );
      return rows;
    });
    if (rows.length === 0) return notFound("intent not found");
    return ok(rows[0]);
  } catch (e) {
    return serverError((e as Error).message);
  }
}

export async function DELETE(req: NextRequest, ctx: Ctx) {
  const auth = authorize(fromWebRequest(req));
  const denied = authResponse(auth);
  if (denied) return denied;
  const id = Number(ctx.params.id);
  if (!Number.isInteger(id)) return bad("id must be an integer");
  try {
    const rows = await withClient(async (c) => {
      const { rows } = await c.query(
        "DELETE FROM intents WHERE id = $1 RETURNING id",
        [id]
      );
      return rows;
    });
    if (rows.length === 0) return notFound("intent not found");
    return ok({ deleted: id });
  } catch (e) {
    return serverError((e as Error).message);
  }
}
