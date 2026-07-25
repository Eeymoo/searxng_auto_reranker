import { NextRequest } from "next/server";
import { authorize, fromWebRequest } from "@/lib/auth";
import { authResponse } from "@/lib/auth_adapter";
import { withClient } from "@/lib/db";
import { ok, bad, serverError } from "@/lib/http";
import { validateNonEmpty } from "@/lib/validation";

type Ctx = { params: { id: string } };

/** POST /api/intents/:id/keywords  body: { keyword } */
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
  const err = validateNonEmpty("keyword", body.keyword);
  if (err) return bad(err.message, err);

  try {
    const rows = await withClient(async (c) => {
      const { rows } = await c.query(
        `INSERT INTO intent_keywords (intent_id, keyword)
         VALUES ($1, $2)
         RETURNING id, intent_id, keyword`,
        [intentId, body.keyword]
      );
      return rows;
    });
    return ok(rows[0], 201);
  } catch (e) {
    // unique violation -> 409-ish
    const msg = (e as Error).message;
    if (msg.includes("unique") || msg.includes("duplicate")) {
      return bad("keyword already exists for this intent");
    }
    return serverError(msg);
  }
}

/** DELETE /api/intents/:id/keywords?keyword=...  or by id ?id=... */
export async function DELETE(req: NextRequest, ctx: Ctx) {
  const auth = authorize(fromWebRequest(req));
  const denied = authResponse(auth);
  if (denied) return denied;
  const intentId = Number(ctx.params.id);
  if (!Number.isInteger(intentId)) return bad("id must be an integer");

  const url = new URL(req.url);
  const kwId = url.searchParams.get("id");
  const keyword = url.searchParams.get("keyword");

  try {
    const rows = await withClient(async (c) => {
      if (kwId) {
        const { rows } = await c.query(
          "DELETE FROM intent_keywords WHERE id = $1 AND intent_id = $2 RETURNING id",
          [Number(kwId), intentId]
        );
        return rows;
      }
      if (keyword) {
        const { rows } = await c.query(
          "DELETE FROM intent_keywords WHERE intent_id = $1 AND keyword = $2 RETURNING id",
          [intentId, keyword]
        );
        return rows;
      }
      return [];
    });
    if (rows.length === 0) return bad("keyword not found");
    return ok({ deleted: rows[0].id });
  } catch (e) {
    return serverError((e as Error).message);
  }
}
