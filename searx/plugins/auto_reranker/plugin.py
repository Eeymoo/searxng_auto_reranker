"""SearXNG plugin entry point.

Registered via settings.yml as
    plugins:
      searx.plugins.auto_reranker.plugin.AutoRerankerPlugin:
        active: true

Implements the ``post_search`` hook to overlay rule + vector re-ranking on
SearXNG's native ranking.  See README.md and docs/ for configuration.

This plugin targets SearXNG 2024+ (granian, new Plugin/PluginCfg API,
ResultContainer.main_results_map).
"""

from __future__ import annotations

import logging
import os
from typing import Any, Optional

# SearXNG plugin API imports (these exist inside the SearXNG container).
from searx.plugins._core import Plugin, PluginCfg, PluginInfo
import searx

from .config_loader import ConfigLoader
from .intent_router import IntentRouter
from .pg_client import PGClient, PGUnavailable
from .rule_engine import ResultRef, RuleEngine
from .vector_engine import PROTOCOL_GENERIC, SUPPORTED_PROTOCOLS, VectorEngine

logger = logging.getLogger("searx.plugins.auto_reranker")


def _result_text(result: Any) -> str:
    """Build the semantic text sent to the reranker.

    Fallback chain per spec vector-rerank "语义文本来源优先级":
      title + " " + content  -> title -> content -> "" (engine then uses URL).
    """
    def _get(obj, name):
        if hasattr(obj, name):
            return getattr(obj, name) or ""
        if hasattr(obj, "get"):
            return obj.get(name) or ""
        return ""

    title = _get(result, "title").strip()
    content = _get(result, "content").strip()
    if title and content:
        return f"{title} {content}"
    return title or content


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


class AutoRerankerPlugin(Plugin):
    """SearXNG plugin: rule + vector re-ranking overlay."""

    id = "auto_reranker"

    def __init__(self, plg_cfg: PluginCfg) -> None:
        super().__init__(plg_cfg)
        self.info = PluginInfo(
            id=self.id,
            name="Auto Reranker",
            description="Configurable rule + vector second-pass re-ranking for SearXNG.",
            preference_section="general",
        )
        self._pg: Optional[PGClient] = None
        self._loader: Optional[ConfigLoader] = None
        self._rules = RuleEngine()
        self._intents = IntentRouter()
        self._vector = VectorEngine(enabled=False)
        self._cfg: dict = {}

    # ------------------------------------------------------------------ #
    # SearXNG lifecycle
    # ------------------------------------------------------------------ #
    def init(self, app) -> bool:  # noqa: D401  pragma: no cover - thin glue
        """Read settings, connect to PG, warm the config cache."""
        try:
            # SearXNG's settings singleton is accessed via searx.get_setting.
            # We read the entire `auto_reranker` block (a dict) at once; if the
            # block is missing, fall back to an empty dict and rely on env vars.
            raw = searx.get_setting("auto_reranker", {}) or {}
            if not isinstance(raw, dict):
                # newer SearXNG may wrap settings in a msgspec.Struct; coerce
                raw = dict(getattr(raw, "__dict__", {}))
            self._cfg = _parse_settings(raw)
        except Exception as exc:  # noqa: BLE001
            logger.error("auto_reranker: cannot read settings: %s", exc)
            return True  # stay loaded but inert; native ranking untouched

        dsn = self._cfg["database_url"]
        if not dsn:
            logger.warning(
                "auto_reranker: no database_url configured; plugin will degrade to native ranking"
            )
            return True

        try:
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
            self._loader.get()  # warm cache at startup
        except Exception as exc:  # noqa: BLE001 - init must never crash
            logger.error("auto_reranker: init pre-load failed: %s", exc)
        return True

    # ------------------------------------------------------------------ #
    # post_search hook
    # ------------------------------------------------------------------ #
    def post_search(self, request, search) -> None:
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

        container = getattr(search, "result_container", None)
        if container is None:
            return

        # SearXNG 2024+ stores results in main_results_map (dict by hash).
        # Older versions had a `results` list property. Support both.
        results_map = getattr(container, "main_results_map", None)
        if results_map is None:
            # Fallback for older SearXNG versions.
            results = getattr(container, "results", None)
            if not results:
                return
            self._rerank_legacy(results, request, search, snapshot)
            return

        if not results_map:
            return

        query = getattr(getattr(request, "search_params", None), "query", "") or ""

        # 1) project each result into a ResultRef for the rule engine.
        items = list(results_map.items())  # [(hash, result_obj), ...]
        refs = []
        for h, r in items:
            url = getattr(r, "url", "") or (r.get("url", "") if hasattr(r, "get") else "")
            score = getattr(r, "score", None)
            if score is None:
                score = r.get("score", 0.0) if hasattr(r, "get") else 0.0
            refs.append(ResultRef(url=str(url), score=float(score), text=_result_text(r)))

        # 2) intent routing + rule rerank
        effective_rules = self._intents.effective_rules(query, snapshot)
        scored = self._rules.rerank(refs, effective_rules)

        # 3) optional vector rerank over top-N
        scored = self._vector.rerank(query, scored)

        # 4) write back: update score on each result obj; drop blacklisted.
        #    SearXNG's ResultContainer will re-sort by score when asked.
        #    Force the sorted cache to be rebuilt.
        new_map = {}
        score_by_url = {s.url: s.final_score for s in scored}
        dropped_urls = {s.url for s in scored if s.dropped}
        for h, r in items:
            url = getattr(r, "url", "") or (r.get("url", "") if hasattr(r, "get") else "")
            if url in dropped_urls:
                continue
            new_score = score_by_url.get(url)
            if new_score is not None and new_score != getattr(r, "score", None):
                try:
                    r.score = new_score  # MainResult (msgspec.Struct)
                except (AttributeError, TypeError):
                    # LegacyResult is a dict
                    if hasattr(r, "__setitem__"):
                        r["score"] = new_score
            new_map[h] = r

        container.main_results_map = new_map
        # Invalidate the ordered cache so get_ordered_results() recomputes.
        if hasattr(container, "_main_results_sorted"):
            try:
                container._main_results_sorted = None
            except (AttributeError, TypeError):
                pass

    def _rerank_legacy(self, results, request, search, snapshot) -> None:
        """Fallback path for old SearXNG (list-based result_container.results)."""
        query = getattr(getattr(request, "search_params", None), "query", "") or ""
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
        scored = self._vector.rerank(query, scored)
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
        search.result_container.results = new_results

    # ------------------------------------------------------------------ #
    def close(self) -> None:  # pragma: no cover
        if self._vector is not None:
            self._vector.close()
        if self._pg is not None:
            self._pg.close()
