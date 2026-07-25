import { NextRequest } from "next/server";
import { authorize, fromWebRequest } from "@/lib/auth";
import { authResponse } from "@/lib/auth_adapter";
import { withClient } from "@/lib/db";
import { ok, bad, serverError } from "@/lib/http";

/**
 * POST /api/test
 *   body: { url: string, query?: string }
 *
 * Evaluates the given URL against ALL currently-stored enabled rules
 * (generic + intent-specific when the query matches an intent) and reports
 * which rule won, the resulting coefficient and whether the URL would be
 * dropped. No data is written.
 */
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
  const url = typeof body.url === "string" ? body.url : "";
  if (!url) return bad("url is required");
  const query = typeof body.query === "string" ? body.query : "";

  try {
    const result = await withClient(async (c) => {
      // Load generic + intent rules in one round-trip via UNION.
      // intent rules participate only when `query` matches a keyword of theirs.
      const { rows } = await c.query(
        `
        WITH matched_intent AS (
          SELECT i.id, i.priority
            FROM intents i
            JOIN intent_keywords k ON k.intent_id = i.id
           WHERE i.enabled
             AND ($2::text = '' OR POSITION(LOWER(k.keyword) IN LOWER($2::text)) > 0)
           ORDER BY i.priority ASC, i.id ASC
           LIMIT 1
        )
        SELECT r.id, r.pattern, r.coefficient, r.priority, r.intent_id,
               r.description,
               -- Direction matters: the URL is matched AGAINST the regex pattern
               -- (URL tilde pattern), NOT pattern tilde URL.
               ($1::text ~ r.pattern) AS hit
          FROM rules r
         WHERE r.enabled
           AND (r.intent_id IS NULL OR r.intent_id = (SELECT id FROM matched_intent))
         ORDER BY r.priority ASC, r.id ASC
        `
        ,
        [url, query]
      );
      return rows;
    });

    // First hit (rules are already ordered by priority asc, id asc).
    const winner = result.find((r: { hit: boolean }) => r.hit) || null;
    const coefficient = winner ? Number(winner.coefficient) : 1.0;
    return ok({
      url,
      query,
      matched_rule: winner,
      coefficient,
      dropped: coefficient === 0,
      evaluated_rule_count: result.length,
    });
  } catch (e) {
    return serverError((e as Error).message);
  }
}
