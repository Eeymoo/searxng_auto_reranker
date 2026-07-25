# Troubleshooting

Common issues and how to diagnose them.

## Plugin has no effect

**Symptoms**: rules exist in the DB but SearXNG's results look unchanged.

**Checks**:

1. Is the plugin loaded? Check SearXNG's plugin list (Settings → Plugins in the UI, or `grep -i "auto_reranker"` in the logs at startup).
2. Is `database_url` reachable from the SearXNG container? `docker exec -it <searxng> python -c "import psycopg2; psycopg2.connect('...')"` should connect.
3. Are your rules `enabled = true`? Disabled rules are skipped silently.
4. Is the cache stale? Click **Refresh now** in config-ui (or wait `cache_ttl` seconds). Watch the plugin log for the `PG unavailable` error — if you see it, the plugin is serving the last cached snapshot (or none at all on first run).

**Log line to look for**: `PG unavailable and no cache: degrading to native ranking` — this means the plugin loaded but has no config at all.

## Vector reranker never changes the order

**Symptoms**: `vector_enabled: true` is set but results don't differ.

**Checks**:

1. Watch for `vector rerank failed, falling back to rule order: <reason>`. Common reasons:
   - `rerank service returned HTTP 401` → wrong/missing `vector_api_key`.
   - `rerank service returned HTTP 404` → wrong `vector_base_url` (don't include `/rerank` in the base).
   - `timed out` → increase `vector_timeout` or use a faster service.
   - `rerank service returned no results` → service responded but with an empty body.
2. Confirm `top_n` is high enough to include the results you expect to move.
3. Confirm `base_url` has **no trailing slash** and that `{base}/rerank` is the correct path.

## A rule I added isn't matching

**Symptoms**: a URL you expect to be boosted/blacklisted is unaffected.

**Checks**:

1. Use the **Test** page: paste the URL and the query, then read the result. If `matched_rule` is null, no enabled rule matched.
2. Python regex syntax differs slightly from JS — escape `.` (`\\.`), anchor when possible (`^https://`), test on [regex101.com (Python flavor)](https://regex101.com/).
3. If multiple rules match, only the **first by `priority`** is applied. Lower the priority of the rule you want to win.
4. Confirm `intent_id` is correct. An intent-specific rule only applies when the query matches that intent's keywords; otherwise it's skipped. Set `intent_id` to NULL for an always-on rule.

## Blacklist removing too much

**Symptoms**: legitimate results disappear.

**Cause**: blacklist patterns (`coefficient = 0`) are too broad.

**Fix**:

- Anchor patterns (`^https://spam\\.example/` rather than `spam`).
- Use the **Test** page against URLs you don't want removed.
- Temporarily disable the suspect rule (`enabled = false`) and verify with Test, then re-tighten the pattern.

## Token lost / locked out

**Symptoms**: cannot access config-ui.

**Recovery**: the token is read from `AUTORERANKER_TOKEN`. Set a new value and restart the config-ui container:

```bash
export AUTORERANKER_TOKEN=$(openssl rand -hex 32)
docker compose restart config-ui
```

The plugin does **not** need a restart — it reads only from PostgreSQL.

## config-ui returns 500 on every request

**Cause**: `AUTORERANKER_TOKEN` is unset on the server. The auth layer refuses every request with HTTP 500 and the message `server misconfigured: missing AUTORERANKER_TOKEN`.

**Fix**: set the env var (see [INSTALL.md](./INSTALL.md)).

## Changes don't propagate to multiple SearXNG instances

Each instance keeps its own TTL cache. After clicking **Refresh now**, instances converge within `cache_ttl` seconds (default 30). For faster convergence, lower `cache_ttl` (at the cost of more DB reads).

## PostgreSQL connection failures

```sql
-- confirm the user can connect and the schema is loaded
psql "$DATABASE_URL" -c '\dt'      # expect: intents, intent_keywords, rules, config_meta
psql "$DATABASE_URL" -c 'SELECT * FROM config_meta;'
```

If `\dt` is empty, re-apply `migrations/001_init.sql`. If you see a CHECK violation on `coefficient`, your value is outside `0.0`–`10.0`.
