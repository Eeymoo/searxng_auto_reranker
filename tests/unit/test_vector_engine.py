"""Unit tests for vector_engine.

Uses a fake HTTP client to avoid real network calls.
"""

from __future__ import annotations

from dataclasses import dataclass

from auto_reranker.vector_engine import VectorEngine


@dataclass
class Item:
    url: str
    native_score: float


class FakeResponse:
    def __init__(self, status_code: int, payload: dict | None):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        if self._payload is None:
            raise ValueError("no json")
        return self._payload


class FakeHTTP:
    """Records last request and returns a queued response."""

    def __init__(self, response=None, *, raise_exc=None):
        self.response = response
        self.raise_exc = raise_exc
        self.last_url = None
        self.last_payload = None
        self.last_headers = None
        self.last_timeout = None

    def post(self, url, json=None, headers=None, timeout=None):
        self.last_url = url
        self.last_payload = json
        self.last_headers = headers
        self.last_timeout = timeout
        if self.raise_exc is not None:
            raise self.raise_exc
        return self.response

    def close(self):
        pass


def _items(n):
    return [Item(url=f"https://x{i}.example/", native_score=float(i)) for i in range(n)]


# --------------------------------------------------------------------------- #
def test_disabled_returns_input_unchanged():
    http = FakeHTTP()
    eng = VectorEngine(enabled=False, base_url="http://v", http_client=http)
    items = _items(3)
    out = eng.rerank("q", items)
    assert out == items
    assert http.last_url is None  # not called


def test_enabled_no_base_url_returns_input_unchanged():
    eng = VectorEngine(enabled=True, base_url="", http_client=FakeHTTP())
    out = eng.rerank("q", _items(3))
    assert out == _items(3)


def test_successful_rerank_reorders_head_by_score():
    # scores descending so order becomes 0,1,2 (highest first -> here ids 2,1,0)
    resp = FakeResponse(
        200,
        {"results": [
            {"id": "2", "score": 0.9},
            {"id": "0", "score": 0.7},
            {"id": "1", "score": 0.8},
        ]},
    )
    http = FakeHTTP(resp)
    eng = VectorEngine(enabled=True, base_url="http://v", top_n=10, http_client=http)
    items = _items(3)
    out = eng.rerank("query", items)
    # expected order by score desc: id2, id1, id0
    assert [o.url for o in out] == ["https://x2.example/", "https://x1.example/", "https://x0.example/"]
    # request shape
    assert http.last_url == "http://v/rerank"
    assert http.last_payload["query"] == "query"
    assert len(http.last_payload["documents"]) == 3
    assert http.last_payload["top_n"] == 3


def test_timeout_silently_falls_back_to_input_order():
    http = FakeHTTP(raise_exc=TimeoutError("simulated"))
    eng = VectorEngine(enabled=True, base_url="http://v", http_client=http, timeout=0.1)
    items = _items(3)
    out = eng.rerank("q", items)
    assert [o.url for o in out] == [i.url for i in items]  # original order


def test_non_2xx_falls_back():
    http = FakeHTTP(FakeResponse(500, None))
    eng = VectorEngine(enabled=True, base_url="http://v", http_client=http)
    items = _items(2)
    out = eng.rerank("q", items)
    assert [o.url for o in out] == [i.url for i in items]


def test_malformed_body_falls_back():
    http = FakeHTTP(FakeResponse(200, {"oops": True}))
    eng = VectorEngine(enabled=True, base_url="http://v", http_client=http)
    items = _items(2)
    out = eng.rerank("q", items)
    assert [o.url for o in out] == [i.url for i in items]


def test_top_n_keeps_tail_in_place():
    # only first 2 of 4 get re-ranked; tail must stay in original relative order
    resp = FakeResponse(
        200,
        {"results": [
            {"id": "0", "score": 0.1},
            {"id": "1", "score": 0.9},
        ]},
    )
    http = FakeHTTP(resp)
    eng = VectorEngine(enabled=True, base_url="http://v", top_n=2, http_client=http)
    items = _items(4)
    out = eng.rerank("q", items)
    # head reordered: id1 then id0 ; tail unchanged: x2, x3
    assert [o.url for o in out] == [
        "https://x1.example/",
        "https://x0.example/",
        "https://x2.example/",
        "https://x3.example/",
    ]


def test_same_vector_score_tiebreaks_by_native_score_desc():
    resp = FakeResponse(
        200,
        {"results": [
            {"id": "0", "score": 0.5},
            {"id": "1", "score": 0.5},
            {"id": "2", "score": 0.5},
        ]},
    )
    http = FakeHTTP(resp)
    eng = VectorEngine(enabled=True, base_url="http://v", top_n=10, http_client=http)
    items = [
        Item("a", 1.0),
        Item("b", 3.0),
        Item("c", 2.0),
    ]
    out = eng.rerank("q", items)
    # equal vector score -> higher native first
    assert [o.url for o in out] == ["b", "c", "a"]


def test_api_key_propagated_to_authorization_header():
    resp = FakeResponse(200, {"results": []})
    http = FakeHTTP(resp)
    eng = VectorEngine(enabled=True, base_url="http://v", api_key="secret", top_n=2, http_client=http)
    eng.rerank("q", _items(2))
    assert http.last_headers.get("Authorization") == "Bearer secret"


# --------------------------------------------------------------------------- #
# protocol-specific request/response shape
# --------------------------------------------------------------------------- #
def test_jina_protocol_sends_texts_and_parses_indexed_array():
    # Service returns a top-level array of {index, score}.
    resp = FakeResponse(
        200,
        [{"index": 1, "score": 0.9}, {"index": 0, "score": 0.1}],
    )
    http = FakeHTTP(resp)
    eng = VectorEngine(
        enabled=True, base_url="http://v", protocol="jina", top_n=10, http_client=http
    )
    items = [Item("a", 1.0), Item("b", 2.0)]
    out = eng.rerank("query", items)
    # request shape
    assert "texts" in http.last_payload
    assert "documents" not in http.last_payload
    assert http.last_payload["texts"] == ["a", "b"]
    # response parsed correctly: index 1 (score 0.9) first
    assert [o.url for o in out] == ["b", "a"]


def test_cohere_protocol_sends_bare_string_documents():
    resp = FakeResponse(
        200,
        {"results": [
            {"index": 0, "relevance_score": 0.8},
            {"index": 1, "relevance_score": 0.2},
        ]},
    )
    http = FakeHTTP(resp)
    eng = VectorEngine(
        enabled=True, base_url="http://v", protocol="cohere", top_n=10, http_client=http
    )
    items = [Item("a", 1.0), Item("b", 2.0)]
    eng.rerank("query", items)
    # Cohere documents is a list of bare strings, not {id,text} objects
    assert http.last_payload["documents"] == ["a", "b"]
    assert all(isinstance(d, str) for d in http.last_payload["documents"])


def test_unknown_protocol_falls_back_to_generic():
    resp = FakeResponse(
        200,
        {"results": [{"id": "0", "score": 0.5}, {"id": "1", "score": 0.9}]},
    )
    http = FakeHTTP(resp)
    eng = VectorEngine(
        enabled=True, base_url="http://v", protocol="bogus", top_n=10, http_client=http
    )
    items = [Item("a", 1.0), Item("b", 2.0)]
    out = eng.rerank("q", items)
    # generic shape used: documents=[{id,text}]
    assert all("id" in d and "text" in d for d in http.last_payload["documents"])
    assert [o.url for o in out] == ["b", "a"]  # id 1 scored higher


def test_jina_protocol_handles_wrapped_results_object():
    # Some jina-compatible services wrap the array in {"results": [...]}.
    resp = FakeResponse(
        200,
        {"results": [{"index": 0, "score": 0.9}, {"index": 1, "score": 0.1}]},
    )
    http = FakeHTTP(resp)
    eng = VectorEngine(
        enabled=True, base_url="http://v", protocol="jina", top_n=10, http_client=http
    )
    items = [Item("a", 1.0), Item("b", 2.0)]
    out = eng.rerank("q", items)
    assert [o.url for o in out] == ["a", "b"]


# --------------------------------------------------------------------------- #
# B2 regression: text source must be content (title+content), not URL
# --------------------------------------------------------------------------- #
@dataclass
class ContentItem:
    url: str
    native_score: float
    text: str = ""


def test_default_text_of_uses_text_field_when_present():
    """Spec: vector reranker receives title+content, NOT the URL."""
    resp = FakeResponse(
        200,
        {"results": [{"id": "0", "score": 0.5}]},
    )
    http = FakeHTTP(resp)
    eng = VectorEngine(
        enabled=True, base_url="http://v", protocol="generic", top_n=10, http_client=http
    )
    items = [ContentItem(url="https://x.gov.cn/news", native_score=1.0,
                         text="国务院今日发布最新政策要点")]
    eng.rerank("今天 新闻", items)
    # The document text sent must be the content, not the URL.
    assert http.last_payload["documents"][0]["text"] == "国务院今日发布最新政策要点"
    assert "gov.cn" not in http.last_payload["documents"][0]["text"]


def test_default_text_of_falls_back_to_url_when_text_empty():
    """Spec: when title/content are both empty, fall back to URL (never throw)."""
    resp = FakeResponse(200, {"results": [{"id": "0", "score": 0.5}]})
    http = FakeHTTP(resp)
    eng = VectorEngine(enabled=True, base_url="http://v", top_n=10, http_client=http)
    # text field absent entirely (duck-typed like the legacy Item dataclass)
    items = [Item("https://x.gov.cn/news", 1.0)]
    eng.rerank("q", items)
    assert http.last_payload["documents"][0]["text"] == "https://x.gov.cn/news"


def test_jina_protocol_also_uses_text_field_not_url():
    resp = FakeResponse(200, [{"index": 0, "score": 0.9}])
    http = FakeHTTP(resp)
    eng = VectorEngine(
        enabled=True, base_url="http://v", protocol="jina", top_n=10, http_client=http
    )
    items = [ContentItem(url="https://weibo.com/hot", native_score=1.0,
                         text="微博热搜榜实时 - 今日热点新闻汇总")]
    eng.rerank("今天热点新闻", items)
    assert http.last_payload["texts"][0] == "微博热搜榜实时 - 今日热点新闻汇总"
    assert "weibo.com" not in http.last_payload["texts"][0]
