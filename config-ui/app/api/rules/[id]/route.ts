import { NextRequest } from "next/server";
import { authorize, fromWebRequest } from "@/lib/auth";
import { authResponse } from "@/lib/auth_adapter";
import { withClient } from "@/lib/db";
import { ok, bad, notFound, serverError } from "@/lib/http";
import { validateCoefficient, validatePattern } from "@/lib/validation";

type Ctx = { params: { id: string } };

async function patchImpl(req: NextRequest, ctx: Ctx) {
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

  if (body.pattern !== undefined) {
    const err = validatePattern(body.pattern);
    if (err) return bad(err.message, err);
    params.push(body.pattern);
    sets.push(`pattern = $${params.length}`);
  }
  if (body.coefficient !== undefined) {
    const err = validateCoefficient(body.coefficient);
    if (err) return bad(err.message, err);
    params.push(body.coefficient);
    sets.push(`coefficient = $${params.length}`);
  }
  if (body.priority !== undefined) {
    const p = Number(body.priority);
    if (!Number.isInteger(p)) return bad("priority must be an integer");
    params.push(p);
    sets.push(`priority = $${params.length}`);
  }
  if (body.intent_id !== undefined) {
    const v =
      body.intent_id === null ? null : Number(body.intent_id);
    if (v !== null && !Number.isInteger(v)) {
      return bad("intent_id must be an integer or null");
    }
    params.push(v);
    sets.push(`intent_id = $${params.length}`);
  }
  if (body.enabled !== undefined) {
    params.push(Boolean(body.enabled));
    sets.push(`enabled = $${params.length}`);
  }
  if (body.description !== undefined) {
    params.push(body.description);
    sets.push(`description = $${params.length}`);
  }

  if (sets.length === 0) return bad("no fields to update");

  params.push(id);
  try {
    const rows = await withClient(async (c) => {
      const { rows } = await c.query(
        `UPDATE rules SET ${sets.join(", ")} WHERE id = $${params.length}
         RETURNING id, pattern, coefficient, priority, intent_id, enabled, description,
                   created_at, updated_at`,
        params
      );
      return rows;
    });
    if (rows.length === 0) return notFound("rule not found");
    return ok(rows[0]);
  } catch (e) {
    return serverError((e as Error).message);
  }
}

export const PATCH = patchImpl;

export async function DELETE(req: NextRequest, ctx: Ctx) {
  const auth = authorize(fromWebRequest(req));
  const denied = authResponse(auth);
  if (denied) return denied;

  const id = Number(ctx.params.id);
  if (!Number.isInteger(id)) return bad("id must be an integer");

  try {
    const rows = await withClient(async (c) => {
      const { rows } = await c.query(
        "DELETE FROM rules WHERE id = $1 RETURNING id",
        [id]
      );
      return rows;
    });
    if (rows.length === 0) return notFound("rule not found");
    return ok({ deleted: id });
  } catch (e) {
    return serverError((e as Error).message);
  }
}
