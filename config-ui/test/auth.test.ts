import test from "node:test";
import assert from "node:assert/strict";

import { authorize, getToken, type AuthInput } from "../lib/auth.ts";

function mkReq(headers: Record<string, string> = {}, cookie = ""): AuthInput {
  return {
    getHeader: (name: string) => headers[name.toLowerCase()] ?? null,
    getCookie: (name: string) =>
      cookie && name === "auto_reranker_token" ? cookie : undefined,
  };
}

test("getToken: throws when env var is missing", () => {
  delete process.env.AUTORERANKER_TOKEN;
  assert.throws(() => getToken(), /AUTORERANKER_TOKEN/);
});

test("authorize: rejects when token is missing on the server (500)", () => {
  delete process.env.AUTORERANKER_TOKEN;
  const r = authorize(mkReq());
  assert.equal(r.ok, false);
  if (!r.ok) assert.equal(r.status, 500);
});

test("authorize: rejects missing Authorization header with 401", () => {
  process.env.AUTORERANKER_TOKEN = "secret";
  const r = authorize(mkReq());
  assert.equal(r.ok, false);
  if (!r.ok) assert.equal(r.status, 401);
});

test("authorize: rejects wrong token", () => {
  process.env.AUTORERANKER_TOKEN = "secret";
  const r = authorize(mkReq({ authorization: "Bearer wrong" }));
  assert.equal(r.ok, false);
  if (!r.ok) assert.equal(r.status, 401);
});

test("authorize: accepts valid Bearer token", () => {
  process.env.AUTORERANKER_TOKEN = "secret";
  const r = authorize(mkReq({ authorization: "Bearer secret" }));
  assert.equal(r.ok, true);
});

test("authorize: accepts valid cookie token", () => {
  process.env.AUTORERANKER_TOKEN = "secret";
  const r = authorize(mkReq({}, "secret"));
  assert.equal(r.ok, true);
});

test("authorize: case-insensitive Bearer prefix", () => {
  process.env.AUTORERANKER_TOKEN = "secret";
  const r = authorize(mkReq({ authorization: "bearer secret" }));
  assert.equal(r.ok, true);
});
