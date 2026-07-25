# Installation

This guide walks through running **SearXNG Auto Reranker** end-to-end: PostgreSQL for config storage, the Python plugin loaded into SearXNG, and the Next.js config UI.

## Architecture

```
┌─────────────┐    reads rules     ┌──────────────┐
│  SearXNG    │ ◀──────────────────│ PostgreSQL   │
│ + plugin    │                     └──────┬───────┘
└──────┬──────┘                            │
       │ post_search:                      │ read/write
       │ rule + vector rerank              │
       ▼                                   ▼
┌─────────────┐                     ┌──────────────┐
│ (optional)  │                     │  config-ui   │
│ Reranker    │ ◀──── HTTP ─────────│  Next.js     │
│  service    │      rerank         └──────────────┘
└─────────────┘
```

## Option A — docker compose (recommended)

A ready-to-use compose file lives in [`../docker/docker-compose.yml`](../docker/docker-compose.yml). It brings up PostgreSQL, SearXNG and config-ui together.

```bash
# 1. Set a strong token (do NOT keep the default).
export AUTORERANKER_TOKEN=$(openssl rand -hex 32)

# 2. Start everything.
cd docker
docker compose up -d

# 3. Apply the schema (the compose file auto-applies 001_init.sql on first run,
#    so this is only needed if you reuse an existing DB volume):
# docker exec -i searxng-auto-reranker-postgres-1 \
#   psql -U auto_reranker -d auto_reranker < ../migrations/001_init.sql
```

Services:
- **SearXNG**: http://localhost:8080
- **config-ui**: http://localhost:3000 (sign in with your `AUTORERANKER_TOKEN`)
- **PostgreSQL**: localhost:5432

### Merge the plugin into an existing SearXNG

Copy [`../searx/plugins/auto_reranker/`](../searx/plugins/auto_reranker/) into your SearXNG container's `plugins/` directory and merge these blocks into your `settings.yml`:

```yaml
plugins:
  - searx.plugins.auto_reranker.plugin.AutoRerankerPlugin

auto_reranker:
  database_url: postgresql://auto_reranker:auto_reranker@postgres:5432/auto_reranker
  cache_ttl: 30
  vector_enabled: false
  vector_base_url: ""
  vector_api_key: ""
  vector_top_n: 20
  vector_timeout: 0.5
```

Install the plugin's Python dependencies inside the SearXNG container:

```bash
pip install -r /usr/local/searxng/searx/plugins/auto_reranker/requirements.txt
```

## Option B — manual setup

### 1. PostgreSQL

```bash
createdb auto_reranker
psql auto_reranker -f migrations/001_init.sql
```

### 2. Plugin

```bash
pip install -r searx/plugins/auto_reranker/requirements.txt
# copy the package into your SearXNG source tree, then merge settings.yml as above
```

### 3. config-ui

```bash
cd config-ui
cp .env.example .env.local
# edit .env.local: set DATABASE_URL and AUTORERANKER_TOKEN
npm install
npm run build
npm start
```

## Environment variables

| Variable                | Required | Used by    | Description                                                       |
| ----------------------- | -------- | ---------- | ----------------------------------------------------------------- |
| `AUTORERANKER_TOKEN`    | yes      | config-ui  | Static bearer token gating all config-ui routes and APIs.         |
| `DATABASE_URL`          | yes      | both       | PostgreSQL DSN (`postgresql://user:pwd@host:5432/db`).            |
| `AUTORERANKER_DATABASE_URL` | alt  | plugin     | Alternative DSN read by the plugin if `DATABASE_URL` is unset.    |
| `AUTORERANKER_VECTOR_API_KEY` | alt | plugin   | Optional bearer token for the reranker service.                   |

## Token security

The token is the **only** thing protecting your config UI. Recommendations:

- Generate a long random string (`openssl rand -hex 32`).
- Inject via environment variable, never commit it.
- Serve config-ui behind TLS (a reverse proxy) or only on an internal network.
- Rotate periodically; rotation requires restarting config-ui but **not** SearXNG.

## Verifying the install

1. Visit http://localhost:3000/login and sign in with the token.
2. Add a rule (e.g. pattern `.*\.gov\.cn/.*`, coefficient `2.0`).
3. Click **Refresh now** (forces the plugin to reload).
4. Search SearXNG; `.gov.cn` results should rank higher.
