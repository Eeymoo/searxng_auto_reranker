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

Two deployment modes — pick the one that matches your situation:

### A. I already have SearXNG running (most common) → **[Overlay deploy guide](docs/OVERLAY_DEPLOY.md)**

Starts just PostgreSQL + config-ui in containers, then mounts the plugin into your existing SearXNG with two volume lines. Your existing settings, engines, themes, Redis are untouched.

### B. Fresh SearXNG + plugin, all in one compose → [Install guide](docs/INSTALL.md)

```bash
cd docker
docker compose --profile full up -d   # starts SearXNG + PG + config-ui
```

After either path, configure rules at `http://<host>:3000` (sign in with your `AUTORERANKER_TOKEN`).

## Documentation

- [Overlay deploy (existing SearXNG)](docs/OVERLAY_DEPLOY.md) — **start here if you already run SearXNG**
- [Install guide (fresh stack)](docs/INSTALL.md)
- [Configuration guide](docs/CONFIG_GUIDE.md)
- [Vector service guide](docs/VECTOR_SERVICE.md)
- [Troubleshooting](docs/TROUBLESHOOTING.md)

## License

MIT
