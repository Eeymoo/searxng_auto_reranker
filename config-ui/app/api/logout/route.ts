import { cookies } from "next/headers";
import { COOKIE_NAME } from "@/lib/auth";
import { ok } from "@/lib/http";

/** POST /api/logout -> clears the auth cookie. */
export async function POST() {
  cookies().set({
    name: COOKIE_NAME,
    value: "",
    httpOnly: true,
    sameSite: "strict",
    path: "/",
    maxAge: 0,  // expire immediately
  });
  return ok({ ok: true });
}
