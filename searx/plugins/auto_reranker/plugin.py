"""SearXNG plugin entry point.

Registered via settings.yml as
    plugins:
      - searx.plugins.auto_reranker.plugin.AutoRerankerPlugin

Implements the ``post_search`` hook to overlay rule + vector re-ranking on
SearXNG's native ranking. See README.md and docs/ for configuration.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Optional

from .config_loader import ConfigLoader
from .intent_router import IntentRouter
from .pg_client import PGClient, PGUnavailable
from .rule_engine import ResultRef, RuleEngine
from .vector_engine import PROTOCOL_GENERIC, SUPPORTED_PROTOCOLS, VectorEngine

logger = logging.getLogger("searx.plugins.auto_reranker")

# SearXNG's plugin API hooks.
plugin_hooks = ("post_search",)


def _result_text(result: dict) -> str:
    """Build the semantic text sent to the reranker for a SearXNG result.

    Fallback chain per spec `vector-rerank` "语义文本来源优先级":
      title + " " + content  -> title -> content -> "" (engine then uses URL).
    """
    title = (result.get("title") or "").strip()
    content = (result.get("content") or "").strip()
    if title and content:
        return f"{title} {content}"
    return title or content  # "" if both empty -> engine falls back to URL


def _parse_settings(raw: dict) -> dict:
    """Read the ``auto_reranker:`` settings block with env-var fallbacks."""
    raw = raw or {}
    return {
        "database_url": raw.get("database_url")
        or os.getenv("AUTORERANKER_DATABASE_URL")
        or os.getenv("DATABASE_URL"),
        "cache_ttl": float(raw.get("cache_ttl", 30)),
        "vector_enabled": bool(raw.get("vector_enabled", False)),
        "vector_base_url": raw.get("vector_base_url", ""),
        "vector_api_key": raw.get("vector_api_key")
        or os.getenv("AUTORERANKER_VECTOR_API_KEY", ""),
        "vector_protocol": raw.get("vector_protocol", PROTOCOL_GENERIC),
        "vector_top_n": int(raw.get("vector_top_n", 20)),
        "vector_timeout": float(raw.get("vector_timeout", 0.5)),
    }


class AutoRerankerPlugin:
    """SearXNG plugin: rule + vector re-ranking overlay."""

    id = "auto_reranker"
    name = "Auto Reranker"
    description = "Configurable rule + vector second-pass re-ranking for SearXNG."
    default_on = False
    # SearXNG reads this to know which hooks we implement.
    plugin_hooks = ("post_search",)

    def __init__(self) -> None:
        self._pg: Optional[PGClient] = None
        self._loader: Optional[ConfigLoader] = None
        self._rules = RuleEngine()
        self._intents = IntentRouter()
        self._vector = VectorEngine(enabled=False)
        self._cfg: dict = {}

    # ------------------------------------------------------------------ #
    # SearXNG lifecycle
    # ------------------------------------------------------------------ #
    def init(self, cfg: Optional[dict] = None) -> None:  # pragma: no cover - thin glue
        self._cfg = _parse_settings(cfg or {})
        dsn = self._cfg["database_url"]
        if not dsn:
            logger.warning(
                "auto_reranker: no database_url configured; plugin will degrade to native ranking"
            )
            return
        self._pg = PGClient(dsn)
        self._loader = ConfigLoader(self._pg, ttl_seconds=self._cfg["cache_ttl"])
        self._vector = VectorEngine(
            enabled=self._cfg["vector_enabled"],
            base_url=self._cfg["vector_base_url"] or None,
            api_key=self._cfg["vector_api_key"] or None,
            protocol=self._cfg["vector_protocol"],
            top_n=self._cfg["vector_top_n"],
            timeout=self._cfg["vector_timeout"],
        )
        try:
            self._loader.get()  # warm cache at startup
        except Exception as exc:  # noqa: BLE001 - init must never crash
            logger.error("auto_reranker: init pre-load failed: %s", exc)

    # ------------------------------------------------------------------ #
    # post_search hook
    # ------------------------------------------------------------------ #
    def post_search(self, request, search) -> None:  # pragma: no cover - SearXNG glue
        try:
            self._do_post_search(request, search)
        except Exception as exc:  # never let reranker break search
            logger.error("auto_reranker: post_search failed: %s", exc)

    def _do_post_search(self, request, search) -> None:
        if self._loader is None:
            return  # not configured; native ranking untouched
        snapshot = self._loader.get()
        if not snapshot.rules and not snapshot.intents:
            return  # empty config -> nothing to do
        result_container = getattr(search, "result_container", None)
        results = getattr(result_container, "results", None) if result_container else None
        if not results:
            return
        query = getattr(getattr(request, "search_params", None), "query", "") or ""

        # 1) project to ResultRef, run rules + intent routing.
        # `text` carries the semantic signal (title + content) consumed by the
        # vector reranker; URL is used only as a last-resort fallback when both
        # are missing. See spec `vector-rerank` "语义文本来源优先级".
        refs = [
            ResultRef(
                url=str(r.get("url", "")),
                score=float(r.get("score", 0.0)),
                text=_result_text(r),
            )
            for r in results
        ]
        effective_rules = self._intents.effective_rules(query, snapshot)
        scored = self._rules.rerank(refs, effective_rules)
        # 2) optional vector rerank over top-N
        scored = self._vector.rerank(query, scored)
        # 3) write back: rebuild results list in the new order, drop blacklisted
        by_url = {r.get("url"): r for r in results}
        new_results = []
        for s in scored:
            original = by_url.get(s.url)
            if original is None:
                continue
            if s.final_score != original.get("score"):
                original = dict(original)
                original["score"] = s.final_score
            new_results.append(original)
        result_container.results = new_results

    # ------------------------------------------------------------------ #
    def close(self) -> None:  # pragma: no cover
        if self._vector is not None:
            self._vector.close()
        if self._pg is not None:
            self._pg.close()
