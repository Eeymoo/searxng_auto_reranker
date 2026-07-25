"""Real end-to-end test for the vector rerank channel.

Talks to the live Jina-v3 reranker at http://192.168.2.79:8080/rerank using the
plugin's VectorEngine (protocol='jina'). Constructs a realistic scenario:

  Query:  「今天热点新闻」
  Results (in native/rule order, intentionally bad):
    1. https://walmart.com/mexico/store-locator     (off-topic but high native score)
    2. https://en.wikipedia.org/wiki/News            (English, barely relevant)
    3. https://weibo.com/hot/search                  (highly relevant, lower score)
    4. https://www.gov.cn/xinwen/2024-01/01/headline (highly relevant)

A good reranker should move the Chinese news/results above Walmart and English wiki.
"""

from __future__ import annotations

import os
import sys
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
PLUGIN = ROOT / "searx" / "plugins"
if str(PLUGIN) not in sys.path:
    sys.path.insert(0, str(PLUGIN))

from dataclasses import dataclass
from auto_reranker.vector_engine import VectorEngine

# Configure via env vars so the live test only runs when explicitly requested.
RERANKER_URL = os.getenv("AUTORERANKER_LIVE_RERANKER_URL", "http://192.168.2.79:8080")
QUERY = "今天热点新闻"

live_required = pytest.mark.skipif(
    os.getenv("AUTORERANKER_RUN_LIVE_VECTOR", "") != "1",
    reason="set AUTORERANKER_RUN_LIVE_VECTOR=1 to run the live reranker test",
)


@dataclass
class Item:
    url: str
    native_score: float
    title: str


def text_of(item: Item) -> str:
    return item.title


# Native order: Walmart first (bad!), Weibo last (semantically best)
ITEMS = [
    Item("https://walmart.com/mexico/store-locator", 10.0,
         "Walmart Mexico Store Locator - Find a store near you"),
    Item("https://en.wikipedia.org/wiki/News", 8.0,
         "News - Wikipedia, the free encyclopedia"),
    Item("https://www.gov.cn/xinwen/2024-01/01/headline.html", 5.0,
         "国务院今日发布最新政策要点与热点新闻"),
    Item("https://weibo.com/hot/search", 3.0,
         "微博热搜榜实时 - 今日热点新闻汇总"),
]


@live_required
def test_live_vector_promotes_semantically_relevant_results():
    eng = VectorEngine(
        enabled=True, base_url=RERANKER_URL, protocol="jina",
        top_n=10, timeout=15.0,
    )
    out = eng.rerank(QUERY, list(ITEMS), text_of=text_of)
    urls = [o.url for o in out]
    # The two Chinese-news results must now beat Walmart and English Wikipedia.
    assert urls.index("https://weibo.com/hot/search") < urls.index(
        "https://walmart.com/mexico/store-locator"
    )
    assert urls.index("https://www.gov.cn/xinwen/2024-01/01/headline.html") < urls.index(
        "https://walmart.com/mexico/store-locator"
    )
    # And Walmart should have dropped to last (semantically least relevant).
    assert urls[-1] == "https://walmart.com/mexico/store-locator"


@live_required
def test_live_vector_timeout_degrades_to_input_order():
    eng = VectorEngine(
        enabled=True, base_url=RERANKER_URL, protocol="jina",
        top_n=10, timeout=0.001,
    )
    out = eng.rerank(QUERY, list(ITEMS), text_of=text_of)
    assert [o.url for o in out] == [i.url for i in ITEMS]  # unchanged


def test_vector_disabled_leaves_order_unchanged():
    eng = VectorEngine(enabled=False, base_url=RERANKER_URL, protocol="jina")
    out = eng.rerank(QUERY, list(ITEMS), text_of=text_of)
    assert [o.url for o in out] == [i.url for i in ITEMS]


# ---------------- standalone runner (python tests/integration/test_vector_e2e_live.py)
def _run(label: str, engine: VectorEngine) -> None:
    print(f"\n=== {label} ===")
    out = engine.rerank(QUERY, list(ITEMS), text_of=text_of)
    for i, it in enumerate(out, 1):
        print(f"  {i}.  {it.url}   [{it.title[:40]}]")


if __name__ == "__main__":
    _run("CONTROL: vector disabled", VectorEngine(enabled=False, base_url=RERANKER_URL, protocol="jina"))
    _run("LIVE: vector=jina", VectorEngine(enabled=True, base_url=RERANKER_URL, protocol="jina",
                                            top_n=10, timeout=15.0))
    _run("DEGRADATION: 1ms timeout", VectorEngine(enabled=True, base_url=RERANKER_URL, protocol="jina",
                                                    top_n=10, timeout=0.001))
