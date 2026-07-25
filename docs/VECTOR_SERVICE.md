# Vector / reranker service

The vector re-rank channel is **optional**. When enabled, the plugin calls an external HTTP service that re-scores the top-N rule-re-ranked results by semantic relevance to the query, then reorders them. If the service is unavailable, slow, or returns malformed data, the plugin silently falls back to the rule-re-ranked order.

## Supported protocols

The plugin supports **three** wire formats, selected via `vector_protocol`:

| `vector_protocol` | Request body                                                                  | Response body                                          | Used by                                                |
| ----------------- | ----------------------------------------------------------------------------- | ------------------------------------------------------ | ------------------------------------------------------ |
| `generic` *(default)* | `{"query", "documents": [{"id","text"}], "top_n"}`                        | `{"results": [{"id","score"}]}`                        | HuggingFace TEI (`--rerank`), home-grown services      |
| `jina`            | `{"query", "texts": [str], "top_n"}`                                          | `[{"index","score"}]` *(top-level array)*              | Jina v3 reranker, BGE-reranker services that mirror it |
| `cohere`          | `{"query", "documents": [str], "top_n"}` *(bare strings)*                    | `{"results": [{"index","relevance_score"}]}`           | Cohere `/v1/rerank`                                    |

Common behaviour across all protocols:

- The plugin always sends N=`vector_top_n` documents; `top_n` is set to the same value.
- The `Authorization: Bearer {vector_api_key}` header is added only when `vector_api_key` is non-empty.
- Scores are arbitrary floats — only the **relative order** is used. Ties fall back to SearXNG's native score (desc).
- A missing/empty/non-list response, a non-2xx status, or a timeout is treated as a failure → silent fallback to the rule-re-ranked order.

## Enabling

In `settings.yml`:

```yaml
auto_reranker:
  vector_enabled: true
  vector_base_url: "http://localhost:8000"   # no trailing slash; /rerank is appended
  vector_api_key: ""                          # bearer token; leave empty if not needed
  vector_protocol: "generic"                  # generic | jina | cohere
  vector_top_n: 20                            # only the top-20 rule-re-ranked results are sent
  vector_timeout: 0.5                         # seconds; on timeout we silently fall back
```

## Self-hosted option: BGE-Reranker via HuggingFace TEI (`protocol: generic`)

[`text-embeddings-inference`](https://github.com/huggingface/text-embeddings-inference) exposes a `/rerank` endpoint that matches the `generic` protocol exactly.

```bash
docker run --gpus all -p 8000:80 \
  -v $PWD/data:/data \
  ghcr.io/huggingface/text-embeddings-inference:latest \
  --model-id BAAI/bge-reranker-v2-m3 \
  --rerank
```

```yaml
vector_base_url: "http://localhost:8000"
vector_protocol: "generic"
vector_api_key: ""        # not needed locally
```

## Self-hosted Jina-v3-style service (`protocol: jina`)

Any service whose `/rerank` accepts `{query, texts: [...]}` and returns a top-level array of `{index, score}` works with `protocol: jina`. For example, a locally-hosted BGE/Jina-compatible reranker exposed via FastAPI:

```bash
# Probe with curl to confirm the shape:
curl -X POST http://<host>:<port>/rerank \
  -H 'Content-Type: application/json' \
  -d '{"query":"今天热点新闻","texts":["微博热搜榜","Walmart Mexico"],"top_n":2}'
# expect: [{"index":0,"score":0.50},{"index":1,"score":0.00001}]
```

```yaml
vector_base_url: "http://<host>:<port>"
vector_protocol: "jina"
vector_api_key: ""        # set if your service requires it
```

> The plugin also tolerates the same array wrapped in `{"results": [...]}` — both shapes parse correctly.

## Managed options

### Cohere (`protocol: cohere`)

```yaml
vector_base_url: "https://api.cohere.ai"
vector_protocol: "cohere"
vector_api_key: "<your Cohere API key>"
```

### Jina AI cloud (`protocol: jina`)

```yaml
vector_base_url: "https://api.jina.ai"
vector_protocol: "jina"
vector_api_key: "<your Jina API key>"
```

## Choosing `top_n` and `timeout`

- `top_n` trades quality for latency/cost. `20` is a sensible default; lower to `10` if your service is slow.
- `timeout` defaults to `0.5s`. Bump to `2.0`–`5.0` for slower self-hosted models — failures still fall back instantly, only slow-but-successful calls add latency.
- Items beyond `top_n` are never sent and keep their rule-re-ranked order.

## Verifying

**End-to-end test against a live reranker** (the repo ships a live test for exactly this):

```bash
# Point at your reranker and enable the live test
export AUTORERANKER_RUN_LIVE_VECTOR=1
export AUTORERANKER_LIVE_RERANKER_URL=http://192.168.2.79:8080   # your service

.venv/bin/python -m pytest tests/integration/test_vector_e2e_live.py -v
```

The live test feeds the plugin a query like 「今天热点新闻」 where the native/rule order is intentionally bad (Walmart above 微博热搜), and asserts that the reranker promotes the semantically relevant Chinese results above the off-topic English/commercial ones. The same script can be run standalone for a readable trace:

```bash
.venv/bin/python tests/integration/test_vector_e2e_live.py
```

Watch the plugin logs (`searx.plugins.auto_reranker.vector_engine`) for warnings like:

```
vector rerank failed, falling back to rule order: <reason>
```

If you see these, check the service URL, protocol selection, API key, and that the response body matches the chosen protocol's shape.
