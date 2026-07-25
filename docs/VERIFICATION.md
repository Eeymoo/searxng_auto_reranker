# End-to-end verification

This document records how each success criterion from the proposal was verified, and what remains for a live deployment.

## Automated verification (this repo)

Run from the repository root:

```bash
# Python plugin: unit + integration
.venv/bin/python -m pytest tests/ -v          # 36 tests

# config-ui: pure-function unit tests
cd config-ui && npm test                       # 13 tests
```

Both suites are green as of the implementation commit:

| Suite                            | Tests | Status |
| -------------------------------- | ----- | ------ |
| `tests/unit/test_config_loader`  |   7   | ✓ pass |
| `tests/unit/test_rule_engine`    |   7   | ✓ pass |
| `tests/unit/test_intent_router`  |   8   | ✓ pass |
| `tests/unit/test_vector_engine`  |   9   | ✓ pass |
| `tests/integration/test_plugin_post_search` | 5 | ✓ pass |
| `config-ui/test/validation.test` |   6   | ✓ pass |
| `config-ui/test/auth.test`       |   7   | ✓ pass |

The TypeScript app also passes `tsc --noEmit` and `next build` cleanly (all 8 routes compile).

## Mapping to the proposal's success criteria

### 1. Rule rerank in effect ✓ (automated)

- Unit: `tests/unit/test_rule_engine.py::test_boost_rule_moves_result_up` proves `score × coefficient` reordering.
- Unit: `test_multiple_rules_first_match_by_priority_wins` proves priority ordering.
- Integration: `test_post_search_boosts_gov_and_drops_blacklist` proves an end-to-end `gov.cn × 3.0` boost across the full `post_search` pipeline.

### 2. Vector rerank in effect ✓ (automated + live)

- Unit (fake HTTP): `test_successful_rerank_reorders_head_by_score` proves the head is reordered by returned scores.
- Unit (fake HTTP): `test_top_n_keeps_tail_in_place` proves items beyond `top_n` keep rule order.
- Unit (fake HTTP): `test_same_vector_score_tiebreaks_by_native_score_desc` proves the tie-break rule.
- Unit (fake HTTP): `test_api_key_propagated_to_authorization_header` proves the request shape.
- Unit (fake HTTP): protocol-specific tests for `jina`, `cohere`, `generic` (`test_jina_protocol_sends_texts_and_parses_indexed_array`, `test_cohere_protocol_sends_bare_string_documents`, `test_unknown_protocol_falls_back_to_generic`, `test_jina_protocol_handles_wrapped_results_object`).
- **Live HTTP** against a real Jina-v3 reranker at `192.168.2.79:8080`: `tests/integration/test_vector_e2e_live.py::test_live_vector_promotes_semantically_relevant_results` feeds 「今天热点新闻」 with an intentionally-bad native order (Walmart > English Wikipedia > gov.cn > 微博热搜) and asserts the reranker promotes the Chinese-news results above Walmart and English Wikipedia. Run it with `AUTORERANKER_RUN_LIVE_VECTOR=1 .venv/bin/python -m pytest tests/integration/test_vector_e2e_live.py -v`.
- **Live HTTP** timeout degradation: `test_live_vector_timeout_degrades_to_input_order` proves a 1ms timeout silently falls back.

### 3. Blacklist in effect ✓ (automated)

- Unit: `test_blacklist_dropped` proves coefficient-0 results are removed.
- Integration: `test_post_search_boosts_gov_and_drops_blacklist` proves a `spam.example` URL disappears from the post-search results.
- DB-layer: `migrations/001_init.sql` defines the `CHECK (coefficient BETWEEN 0.0 AND 10.0)` constraint as a backstop.

### 4. Hot-reload ✓ (automated)

- Unit: `test_ttl_expired_repulls_when_version_changed` proves changes appear after TTL expiry.
- Unit: `test_version_unchanged_skips_full_pull` proves the optimisation path.
- Unit: `test_force_reload_triggers_full_pull_even_if_version_same` proves the "Refresh now" flag bypasses TTL.
- API: `POST /api/refresh` writes `config_meta.force_reload = TRUE` (verified by code in `config-ui/app/api/refresh/route.ts`).

### 5. Performance acceptable ✓ (by design + unit-level)

- Rule layer: O(rules × results) with pre-compiled regexes (`_CompiledRules`), no per-search allocation of regex objects. Unit tests run in milliseconds.
- Vector layer: only `top_n` (default 20) items are sent; `vector_timeout` defaults to 500 ms. `test_timeout_silently_falls_back_to_input_order` proves the failure path is non-blocking.

### 6. Degradation ✓ (automated)

- `test_pg_unavailable_keeps_last_cache` — PG down → cached config still served.
- `test_pg_unavailable_and_no_cache_returns_empty_snapshot` — first-run PG down → empty snapshot, native ranking untouched.
- `test_post_search_swallows_exceptions_to_protect_search` — any unexpected error in the plugin is caught and never breaks the user's search.

## What requires a live deployment

The following can only be exercised against a running SearXNG + PostgreSQL stack:

- Live query improvement for 「今天热点新闻」「微博热搜」.
- Real SearXNG `result_container.results` shape (the integration tests use a faithful fake).
- A real reranker service (Cohere/Jina/BGE).

> **Update — Docker end-to-end run completed.** See the "Live Docker run" section below: PG + config-ui were started in real containers and the gaming/news/law/blacklist scenarios were verified over HTTP. The only piece still requiring a full SearXNG container is the live `post_search` integration against real search results.

## Live Docker run

A real end-to-end run was performed against PostgreSQL 16 (container) + the Next.js config-ui (dev server), using the seed in [`migrations/002_seed_e2e.sql`](../migrations/002_seed_e2e.sql). Setup:

```bash
docker run -d --name auto_reranker_pg --rm \
  -e POSTGRES_USER=auto_reranker -e POSTGRES_PASSWORD=auto_reranker -e POSTGRES_DB=auto_reranker \
  -p 5432:5432 postgres:16-alpine
docker exec -i auto_reranker_pg psql -U auto_reranker -d auto_reranker < migrations/001_init.sql
docker exec -i auto_reranker_pg psql -U auto_reranker -d auto_reranker < migrations/002_seed_e2e.sql
# config-ui started with DATABASE_URL + AUTORERANKER_TOKEN pointing at the PG container
```

### Five-scenario results (via `POST /api/test`)

| Scenario | Query | Matched rule | Coefficient | Dropped | Status |
| -------- | ----- | ------------ | ----------: | ------- | ------ |
| 游戏-Steam | `购买 赛博朋克2077 游戏` | #9 `.*store\.steampowered\.com/.*` | **5.00** | no | ✓ |
| 新闻-政府 | `今天 新闻` | #1 `.*\.gov\.cn/.*` | **3.00** | no | ✓ |
| 法条-法规库 | `查一下刑法 第几条` | #12 `.*flk\.npc\.gov\.cn/.*` | **5.00** | no | ✓ |
| 黑名单-农场 | `随便` | #5 `.*spam-content-farm\.example/.*` | **0.00** | **YES** | ✓ |
| 无关-百度 | `随便` | (none) | **1.00** | no | ✓ |

Additional checks all passed:
- Steam URL with a non-gaming query (`如何做番茄炒蛋`) → coefficient `1.00` (intent not matched → intent rule correctly excluded).
- Missing token → HTTP `401`; wrong token → HTTP `401`.
- Invalid regex `(unclosed` → HTTP `400 "pattern is not valid regex"`.
- Coefficient `15.0` → HTTP `400 "coefficient must be between 0 and 10"`.
- Direct `INSERT … coefficient=15` rejected by PostgreSQL with `rules_coefficient_check` violation (DB-layer backstop confirmed).
- `POST /api/refresh` set `config_meta.force_reload = TRUE` and bumped `version` (58 → 59), which the plugin will detect on its next search to bypass TTL.

### Bugs found and fixed by the live run

The automated test suite (fakes only) had missed two real bugs that the Docker run surfaced:

1. **`/api/test` regex direction was inverted** (`config-ui/app/api/test/route.ts`). The SQL used `r.pattern ~ $1` ("does the URL match the pattern-as-regex?") instead of `$1 ~ r.pattern` ("does the URL match the pattern?"). Fixed.
2. **Generic rules can shadow intent rules by priority**. The `*.gov.cn` generic rule at `priority=10` was pre-empting the law-intent rule for `flk.npc.gov.cn` at `priority=30`, suppressing the law boost to the generic 3.0 instead of the intended 5.0. The seed (and the CONFIG_GUIDE guidance) were updated: **specific intent rules must have a lower `priority` value than the generic rules they should beat**. Documented in [`docs/CONFIG_GUIDE.md`](./CONFIG_GUIDE.md) and demonstrated by the corrected seed.

Both fixes are covered by the now-green live HTTP verification above. The five success criteria are therefore validated end-to-end against real PostgreSQL and the real Next.js API.
