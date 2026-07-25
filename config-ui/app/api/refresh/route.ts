import { NextRequest } from "next/server";
import { authorize, fromWebRequest } from "@/lib/auth";
import { authResponse } from "@/lib/auth_adapter";
import { withClient } from "@/lib/db";
import { ok, serverError } from "@/lib/http";

/**
 * POST /api/refresh
 *
 * Sets config_meta.force_reload = TRUE. Every SearXNG plugin instance reading
 * the same DB checks this flag on its next search and, if set, bypasses its
 * TTL and reloads the full config, then clears the flag.
 */
export async function POST(req: NextRequest) {
  const auth = authorize(fromWebRequest(req));
  const denied = authResponse(auth);
  if (denied) return denied;
  try {
    await withClient(async (c) => {
      await c.query(
        `UPDATE config_meta
            SET force_reload = TRUE,
                updated_at = NOW(),
                version = version + 1
          WHERE id = 1`
      );
    });
    return ok({ force_reload: true });
  } catch (e) {
    return serverError((e as Error).message);
  }
}
