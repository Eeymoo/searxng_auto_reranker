"""Vector re-ranker: optional semantic re-scoring via an external HTTP service.

Talks to any service implementing one of the supported rerank protocols.
Set ``protocol`` to one of:

* ``generic`` (default)
      request:  {"query": ..., "documents": [{"id", "text"}], "top_n": N}
      response: {"results": [{"id", "score"}]}
      Matches HuggingFace TEI (with ``--rerank``) and any home-grown service
      that follows the same shape.

* ``jina``
      request:  {"query": ..., "texts": [str, ...], "top_n": N}
      response: [{"index": int, "score": float}, ...]   (top-level array)
      Matches Jina v3 reranker and the BGE/Jina-style services that mirror it.

* ``cohere``
      request:  {"query": ..., "documents": [str, ...], "top_n": N}
      response: {"results": [{"index", "relevance_score"}]}
      Matches Cohere's /v1/rerank endpoint.

On any failure (timeout, non-2xx, malformed body) it silently falls back to
the input order so the rule-re-ranked list is preserved.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Optional

logger = logging.getLogger("searx.plugins.auto_reranker.vector_engine")

DEFAULT_TOP_N = 20
DEFAULT_TIMEOUT = 0.5  # seconds

PROTOCOL_GENERIC = "generic"
PROTOCOL_JINA = "jina"
PROTOCOL_COHERE = "cohere"
SUPPORTED_PROTOCOLS = (PROTOCOL_GENERIC, PROTOCOL_JINA, PROTOCOL_COHERE)


class VectorEngine:
    def __init__(
        self,
        *,
        enabled: bool = False,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        top_n: int = DEFAULT_TOP_N,
        timeout: float = DEFAULT_TIMEOUT,
        protocol: str = PROTOCOL_GENERIC,
        http_client: Any = None,  # injectable for tests
    ) -> None:
        self.enabled = bool(enabled)
        self.base_url = (base_url or "").rstrip("/")
        self.api_key = api_key
        self.top_n = int(top_n)
        self.timeout = float(timeout)
        self.protocol = protocol if protocol in SUPPORTED_PROTOCOLS else PROTOCOL_GENERIC
        self._http = http_client  # lazily created httpx.Client if None

    # ------------------------------------------------------------------ #
    def rerank(
        self,
        query: str,
        scored: list[Any],  # list of ScoredResult (duck-typed: .url .native_score)
        *,
        text_of: Optional[Callable[[Any], str]] = None,
    ) -> list[Any]:
        """Re-score the top-N entries; return a new ordered list.

        Items beyond top-N keep their relative order. Items within top-N are
        reordered by the reranker's score; ties fall back to native_score.
        """
        if not self.enabled or not self.base_url or not query or not scored:
            return list(scored)

        head = scored[: self.top_n]
        tail = scored[self.top_n :]
        if not head:
            return list(scored)

        text_of = text_of or _default_text_of
        texts = [text_of(item) for item in head]

        scores: Optional[list[float]] = None
        try:
            scores = self._call_service(query, texts)
        except Exception as exc:  # noqa: BLE001 - any failure degrades gracefully
            logger.warning("vector rerank failed, falling back to rule order: %s", exc)
            return list(scored)

        if scores is None or len(scores) != len(head):
            logger.warning("vector rerank returned malformed response, falling back")
            return list(scored)

        # Attach vector score and re-sort head; tie-break by native score desc.
        indexed = list(enumerate(head))
        indexed.sort(
            key=lambda pair: (-scores[pair[0]], -pair[1].native_score, pair[0])
        )
        reordered_head = [item for _, item in indexed]
        return [*reordered_head, *tail]

    # ------------------------------------------------------------------ #
    def _call_service(self, query: str, texts: list[str]) -> Optional[list[float]]:
        client = self._ensure_client()
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        payload, parser = self._protocol_payload_and_parser(query, texts)
        resp = client.post(
            f"{self.base_url}/rerank",
            json=payload,
            headers=headers,
            timeout=self.timeout,
        )
        if resp.status_code // 100 != 2:
            raise RuntimeError(f"rerank service returned HTTP {resp.status_code}")
        data = resp.json()
        results = parser(data)
        # Missing / non-list / empty results => malformed => fall back.
        if not isinstance(results, list) or not results:
            raise RuntimeError("rerank service returned no results")
        # Materialise a score list parallel to the input `texts` order.
        scores = [0.0] * len(texts)
        for entry in results:
            idx, score = entry
            if 0 <= idx < len(scores):
                scores[idx] = score
        # If every score is still zero we treat it as "no useful signal" and
        # fall back, so an all-zero response doesn't silently reshuffle.
        if not any(s > 0.0 for s in scores):
            # Distinguish legitimate all-equal scores (rare) from "service didn't
            # return any of our ids". The latter is the common failure mode.
            seen_ids = {entry[0] for entry in results}
            if seen_ids and seen_ids.issubset(set(range(len(texts)))):
                # Legitimate: all returned indices valid but scores all 0.
                return scores
            raise RuntimeError("rerank service returned scores for unknown indices")
        return scores

    # ------------------------------------------------------------------ #
    # protocol-specific request builders + response parsers
    # ------------------------------------------------------------------ #
    def _protocol_payload_and_parser(
        self, query: str, texts: list[str]
    ) -> tuple[dict, Callable[[Any], list[tuple[int, float]]]]:
        n = len(texts)
        if self.protocol == PROTOCOL_JINA:
            payload = {"query": query, "texts": texts, "top_n": n}
            return payload, _parse_jina
        if self.protocol == PROTOCOL_COHERE:
            # Cohere takes bare string documents.
            payload = {"query": query, "documents": texts, "top_n": n}
            return payload, _parse_cohere
        # generic
        payload = {
            "query": query,
            "documents": [{"id": str(i), "text": t} for i, t in enumerate(texts)],
            "top_n": n,
        }
        return payload, _parse_generic

    # ------------------------------------------------------------------ #
    def _ensure_client(self):
        if self._http is not None:
            return self._http
        try:
            import httpx  # type: ignore
        except ImportError as exc:  # pragma: no cover - dependency guard
            raise RuntimeError("httpx is not installed") from exc
        self._http = httpx.Client()
        return self._http

    def close(self) -> None:
        if self._http is not None:
            try:
                self._http.close()
            except Exception:  # noqa: BLE001
                pass
            self._http = None


# ---------------------------------------------------------------------- #
# response parsers — each returns a list of (index, score)
# ---------------------------------------------------------------------- #
def _default_text_of(item: Any) -> str:
    """Default semantic-text extractor.

    The vector rerank channel must operate on **content**, not URLs (URLs carry
    almost no semantic signal and would degrade the reranker to a weak URL
    matcher — see spec `vector-rerank` "语义文本来源优先级"). ScoredResult
    carries a `text` field populated from the result's title+content by the
    plugin; we fall back to URL only when the text is empty/missing so the
    reranker call still works (never throws).
    """
    text = getattr(item, "text", "") or ""
    text = text.strip()
    if text:
        return text
    return getattr(item, "url", "")


def _parse_generic(data: Any) -> list[tuple[int, float]]:
    """{"results": [{"id": "0", "score": 0.5}]} -> [(0, 0.5)]"""
    results = data.get("results") if isinstance(data, dict) else None
    if not isinstance(results, list):
        return []
    out: list[tuple[int, float]] = []
    for r in results:
        try:
            idx = int(r.get("id"))
            score = float(r.get("score", 0.0))
        except (TypeError, ValueError):
            continue
        out.append((idx, score))
    return out


def _parse_jina(data: Any) -> list[tuple[int, float]]:
    """top-level [{"index": 0, "score": 0.5}] -> [(0, 0.5)]"""
    if not isinstance(data, list):
        # Some Jina-compatible services wrap in {"results": [...]}.
        if isinstance(data, dict):
            data = data.get("results")
        if not isinstance(data, list):
            return []
    out: list[tuple[int, float]] = []
    for r in data:
        try:
            idx = int(r.get("index"))
            score = float(r.get("score", 0.0))
        except (TypeError, ValueError):
            continue
        out.append((idx, score))
    return out


def _parse_cohere(data: Any) -> list[tuple[int, float]]:
    """{"results": [{"index": 0, "relevance_score": 0.5}]} -> [(0, 0.5)]"""
    results = data.get("results") if isinstance(data, dict) else None
    if not isinstance(results, list):
        return []
    out: list[tuple[int, float]] = []
    for r in results:
        try:
            idx = int(r.get("index"))
            # Cohere uses relevance_score; accept score as a fallback.
            score = float(r.get("relevance_score", r.get("score", 0.0)))
        except (TypeError, ValueError):
            continue
        out.append((idx, score))
    return out
