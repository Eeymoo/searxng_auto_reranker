"""Integration test for the Auto Reranker plugin's post_search orchestration.

Uses a fake PG (no real DB) and fakes for SearXNG's request / search /
result_container shapes. Verifies the full pipeline:
   intent routing -> rule rerank -> blacklist drop -> vector rerank -> write-back.
"""

from __future__ import annotations

import sys
import pathlib

# add plugin dir to path
ROOT = pathlib.Path(__file__).resolve().parents[2]
PLUGIN = ROOT / "searx" / "plugins"
if str(PLUGIN) not in sys.path:
    sys.path.insert(0, str(PLUGIN))

from auto_reranker.plugin import AutoRerankerPlugin  # noqa: E402
from auto_reranker.models import Intent, Rule  # noqa: E402


# --------------------------------------------------------------------------- #
# fakes
# --------------------------------------------------------------------------- #
class FakePG:
    def __init__(self):
        self.meta = {"version": 1, "force_reload": False}
        self.rule_rows = []
        self.intent_rows = []
        self.kw_rows = []

    def fetchone(self, sql, params=None):
        return dict(self.meta)

    def fetchall(self, sql, params=None):
        if "FROM rules" in sql:
            return list(self.rule_rows)
        if "FROM intents" in sql:
            return list(self.intent_rows)
        if "intent_keywords" in sql:
            return list(self.kw_rows)
        return []

    def execute(self, sql, params=None):
        pass


class FakeResultContainer:
    def __init__(self, results):
        self.results = results


class FakeSearch:
    def __init__(self, results):
        self.result_container = FakeResultContainer(results)


class FakeSearchParams:
    def __init__(self, query):
        self.query = query


class FakeRequest:
    def __init__(self, query):
        self.search_params = FakeSearchParams(query)


def _result(url, score, title="", content=""):
    return {"url": url, "score": score, "title": title, "content": content}


# --------------------------------------------------------------------------- #
def _build_plugin(pg: FakePG, vector_enabled=False):
    plugin = AutoRerankerPlugin()
    # Bypass init()'s real PGClient construction; inject our fakes directly.
    from auto_reranker.config_loader import ConfigLoader
    from auto_reranker.vector_engine import VectorEngine

    plugin._pg = pg  # not used by tests but keeps attribute consistent
    plugin._loader = ConfigLoader(pg, ttl_seconds=60)
    plugin._vector = VectorEngine(enabled=vector_enabled, base_url="")
    return plugin


def _seed_gaming_rules(pg: FakePG):
    pg.rule_rows = [
        # generic gov boost
        {"id": 1, "pattern": r".*\.gov\.cn/.*", "coefficient": 3.0, "priority": 10,
         "intent_id": None, "enabled": True, "description": None},
        # blacklist spam
        {"id": 2, "pattern": r".*spam\.example/.*", "coefficient": 0.0, "priority": 20,
         "intent_id": None, "enabled": True, "description": None},
        # gaming-intent-only Steam boost
        {"id": 3, "pattern": r".*steampowered\.com/.*", "coefficient": 5.0, "priority": 30,
         "intent_id": 5, "enabled": True, "description": None},
    ]
    pg.intent_rows = [
        {"id": 5, "name": "gaming", "priority": 10, "enabled": True},
    ]
    pg.kw_rows = [{"intent_id": 5, "keyword": "steam"}]


# --------------------------------------------------------------------------- #
def test_post_search_boosts_gov_and_drops_blacklist():
    pg = FakePG()
    _seed_gaming_rules(pg)
    plugin = _build_plugin(pg)

    results = [
        _result("https://blog.example/news", 10.0, "blog"),
        _result("https://www.gov.cn/news/1", 4.0, "gov"),
        _result("https://spam.example/x", 999.0, "spam"),  # blacklisted, must disappear
    ]
    search = FakeSearch(results)
    plugin.post_search(FakeRequest("今天 新闻"), search)

    out = search.result_container.results
    urls = [r["url"] for r in out]
    assert "https://spam.example/x" not in urls
    # gov's final = 4*3=12 > blog 10 -> gov first
    assert urls[0] == "https://www.gov.cn/news/1"
    assert out[0]["score"] == 12.0


def test_post_search_intent_routing_applies_steam_boost_for_gaming_query():
    pg = FakePG()
    _seed_gaming_rules(pg)
    plugin = _build_plugin(pg)

    results = [
        _result("https://store.steampowered.com/app/1", 1.0, "steam"),
        _result("https://blog.example/post", 8.0, "blog"),
    ]
    search = FakeSearch(results)
    # query contains "steam" -> gaming intent matched -> Steam rule applies
    plugin.post_search(FakeRequest("买 steam 游戏"), search)

    out = search.result_container.results
    # steam final = 1*5=5 ; blog final = 8 -> blog still first because 8 > 5
    # To prove Steam rule is active, give it a higher native:
    results2 = [
        _result("https://store.steampowered.com/app/1", 2.0, "steam"),
        _result("https://blog.example/post", 8.0, "blog"),
    ]
    search2 = FakeSearch(results2)
    plugin.post_search(FakeRequest("买 steam 游戏"), search2)
    out2 = search2.result_container.results
    # steam 2*5=10 > blog 8 -> steam first
    assert out2[0]["url"].startswith("https://store.steampowered.com")
    assert out2[0]["score"] == 10.0


def test_post_search_intent_not_matched_skips_intent_rules():
    pg = FakePG()
    _seed_gaming_rules(pg)
    plugin = _build_plugin(pg)

    results = [
        _result("https://store.steampowered.com/app/1", 2.0, "steam"),
        _result("https://blog.example/post", 8.0, "blog"),
    ]
    search = FakeSearch(results)
    # No "steam" keyword -> gaming intent NOT matched -> Steam rule NOT applied
    plugin.post_search(FakeRequest("今天新闻"), search)
    out = search.result_container.results
    # steam final = 2 (coeff 1.0) ; blog final = 8 -> blog first, steam second
    assert out[0]["url"] == "https://blog.example/post"
    assert out[1]["score"] == 2.0  # unchanged


def test_post_search_swallows_exceptions_to_protect_search():
    pg = FakePG()
    _seed_gaming_rules(pg)
    plugin = _build_plugin(pg)

    search = FakeSearch([])
    # Pass an object that will break attribute access internally but should be caught
    plugin.post_search(None, search)  # request is None -> _do_post_search raises
    # If the plugin swallowed the error, search's (empty) results remain unchanged
    assert search.result_container.results == []


def test_init_without_database_url_does_not_crash():
    plugin = AutoRerankerPlugin()
    plugin.init(cfg={})  # no database_url
    assert plugin._loader is None  # degraded: native ranking path


# --------------------------------------------------------------------------- #
# B2 regression: plugin must extract title+content and feed the vector reranker
# --------------------------------------------------------------------------- #
def test_post_search_passes_title_content_to_vector_reranker():
    """Spec vector-rerank: text sent to reranker must be content, not URL."""
    pg = FakePG()
    # Seed at least one rule so the plugin doesn't short-circuit before the
    # vector stage (the early return is `if not snapshot.rules`).
    pg.rule_rows = [
        {"id": 1, "pattern": r".*", "coefficient": 1.0, "priority": 100,
         "intent_id": None, "enabled": True, "description": None},
    ]
    plugin = _build_plugin(pg, vector_enabled=True)
    recorded = {}

    class SpyVector:
        enabled = True
        base_url = "http://spy"

        def rerank(self, query, scored, *, text_of=None):
            recorded["query"] = query
            # Use the engine's default extractor to mirror real behaviour.
            from auto_reranker.vector_engine import _default_text_of
            recorded["texts"] = [_default_text_of(s) for s in scored]
            return list(scored)

    plugin._vector = SpyVector()

    results = [
        _result("https://weibo.com/hot/search", 1.0,
                title="微博热搜榜", content="今日热点新闻汇总"),
        _result("https://walmart.com/x", 2.0,
                title="Walmart", content="Find a store"),
    ]
    search = FakeSearch(results)
    plugin.post_search(FakeRequest("今天热点新闻"), search)

    assert recorded["query"] == "今天热点新闻"
    # The two texts sent to the reranker are the title+content of each result
    # (NOT the URLs). Order follows native score (Walmart 2.0 > Weibo 1.0).
    assert "微博热搜榜 今日热点新闻汇总" in recorded["texts"]
    assert "Walmart Find a store" in recorded["texts"]
    # And critically, no URL leaked into the document texts.
    assert all("weibo.com" not in t and "walmart.com" not in t for t in recorded["texts"])


def test_post_search_text_fallback_to_url_when_no_title_or_content():
    """Spec: title -> content -> URL fallback; never throws."""
    pg = FakePG()
    pg.rule_rows = [
        {"id": 1, "pattern": r".*", "coefficient": 1.0, "priority": 100,
         "intent_id": None, "enabled": True, "description": None},
    ]
    plugin = _build_plugin(pg, vector_enabled=True)
    recorded = {}

    class SpyVector:
        enabled = True
        base_url = "http://spy"

        def rerank(self, query, scored, *, text_of=None):
            from auto_reranker.vector_engine import _default_text_of
            recorded["texts"] = [_default_text_of(s) for s in scored]
            return list(scored)

    plugin._vector = SpyVector()
    results = [_result("https://only-url.example/", 1.0)]  # no title/content
    search = FakeSearch(results)
    plugin.post_search(FakeRequest("q"), search)
    assert recorded["texts"][0] == "https://only-url.example/"
