# SearXNG Auto Reranker

A fully SearXNG-plugin-compatible reranker that overlays a configurable **rule-based** and **vector-based** second-pass re-ranking on top of SearXNG's native ranking. Designed primarily for the poor relevance of Chinese query scenarios (e.g. searching "今天热点新闻" returning irrelevant foreign results), it lets operators boost authoritative Chinese sources, demote/ blacklist low-quality domains, and optionally call an external reranker/embedding service for semantic relevance — all without rewriting SearXNG's frontend or native scoring.

## Features

- **Rule rerank** — URL-regex rules with a coefficient (`score × coefficient`). Coefficient `0` drops the result entirely (blacklist).
- **Intent routing** — keyword → intent mapping (e.g. `gaming` → boost Steam) so authoritative sites are prioritized per query intent.
- **Vector rerank** (optional) — calls an external reranker HTTP service (`POST /rerank`) over the top-N results for semantic re-scoring; fails open (silent fallback) on timeout/error.
- **Hot-reloadable config** — rules, intents, keywords and blacklist live in PostgreSQL; changes take effect within a configurable TTL (default 30s) without restarting SearXNG.
- **Minimal web config UI** — Bun.js + Next.js (App Router) + shadcn/ui, gated by a single static token (`AUTORERANKER_TOKEN`). CRUD for rules, intents, keywords and blacklist, plus a rule tester and a "refresh now" button.

## Repository layout

```
searx/plugins/auto_reranker/   Python plugin (loaded by SearXNG)
config-ui/                     Next.js configuration system
migrations/                    PostgreSQL schema migrations
docker/                        Dockerfiles & compose
docs/                          Install/config/troubleshooting guides
tests/                         Unit & integration tests
```

## Quick start

See [`docs/INSTALL.md`](docs/INSTALL.md) for the full guide. In short:

1. Start PostgreSQL and apply `migrations/001_init.sql`.
2. Drop the plugin into your SearXNG instance and register it in `settings.yml`.
3. Run the `config-ui` container with `AUTORERANKER_TOKEN` and `DATABASE_URL` set.
4. Configure rules in the UI; they take effect within the TTL.

## Documentation

- [Install guide](docs/INSTALL.md)
- [Configuration guide](docs/CONFIG_GUIDE.md)
- [Vector service guide](docs/VECTOR_SERVICE.md)
- [Troubleshooting](docs/TROUBLESHOOTING.md)

## License

MIT
