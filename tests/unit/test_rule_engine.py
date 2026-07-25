"""Unit tests for rule_engine."""

from __future__ import annotations

from auto_reranker.models import Rule
from auto_reranker.rule_engine import ResultRef, RuleEngine


def _rule(rule_id, pattern, coeff, priority=100, intent_id=None, enabled=True):
    return Rule(
        rule_id=rule_id,
        pattern=pattern,
        coefficient=coeff,
        priority=priority,
        intent_id=int_id,
        enabled=enabled,
        description=None,
    ) if False else Rule(  # keep type-checker happy; build directly
        rule_id=rule_id,
        pattern=pattern,
        coefficient=coeff,
        priority=priority,
        intent_id=intent_id,
        enabled=enabled,
        description=None,
    )


# helper to avoid the trick above
def mk(rule_id, pattern, coeff, priority=100, intent_id=None, enabled=True):
    return Rule(
        rule_id=rule_id,
        pattern=pattern,
        coefficient=coeff,
        priority=priority,
        intent_id=intent_id,
        enabled=enabled,
        description=None,
    )


def _ref(url, score):
    return ResultRef(url=url, score=score)


# --------------------------------------------------------------------------- #
def test_boost_rule_moves_result_up():
    engine = RuleEngine()
    rules = [mk(1, r".*\.gov\.cn/.*", 2.0, priority=10)]
    results = [
        _ref("https://blog.example/post", 10.0),
        _ref("https://www.example.gov.cn/news", 5.0),
    ]
    out = engine.rerank(results, rules)
    # gov url gets 5*2=10 -> tie with blog 10 -> tie broken by native score
    # gov native 5 < blog native 10, so blog stays first. Confirm via positions:
    assert out[0].final_score == 10.0
    # Make gov's native strictly lower so boost clearly changes order:
    rules = [mk(1, r".*\.gov\.cn/.*", 3.0, priority=10)]
    out = engine.rerank(results, rules)
    assert out[0].url.endswith(".gov.cn/news")
    assert out[0].final_score == 15.0


def test_blacklist_dropped():
    engine = RuleEngine()
    rules = [mk(2, r".*spam\.example/.*", 0.0)]
    results = [
        _ref("https://good.example/a", 5.0),
        _ref("https://spam.example/b", 100.0),  # would be top, but blacklisted
    ]
    out = engine.rerank(results, rules)
    assert [o.url for o in out] == ["https://good.example/a"]
    # No dropped item leaks through
    assert all(not o.dropped for o in out)


def test_multiple_rules_first_match_by_priority_wins():
    engine = RuleEngine()
    rules = [
        mk(10, r".*\.gov\.cn/.*", 5.0, priority=50),  # later in list, higher priority (lower number)
        mk(20, r".*\.gov\.cn/news.*", 1.0, priority=100),  # lower priority
    ]
    results = [_ref("https://x.gov.cn/news/1", 1.0)]
    out = engine.rerank(results, rules)
    # priority 50 wins -> coeff 5.0 -> final 5.0
    assert out[0].matched_rule_id == 10
    assert out[0].final_score == 5.0


def test_no_match_keeps_coefficient_one():
    engine = RuleEngine()
    rules = [mk(1, r"^never-matches$", 9.0)]
    results = [_ref("https://example.com/x", 7.0)]
    out = engine.rerank(results, rules)
    assert out[0].final_score == 7.0
    assert out[0].matched_rule_id is None


def test_stable_sort_same_final_score_uses_native_desc():
    engine = RuleEngine()
    # both match coeff 1.0 -> final equals native; higher native first
    rules = [mk(1, r".*", 1.0)]
    results = [
        _ref("https://a.example/", 3.0),
        _ref("https://b.example/", 7.0),
        _ref("https://c.example/", 5.0),
    ]
    out = engine.rerank(results, rules)
    assert [o.native_score for o in out] == [7.0, 5.0, 3.0]


def test_disabled_rule_ignored():
    engine = RuleEngine()
    rules = [mk(1, r".*\.gov\.cn/.*", 5.0, enabled=False)]
    results = [_ref("https://x.gov.cn/", 2.0)]
    out = engine.rerank(results, rules)
    assert out[0].final_score == 2.0  # rule skipped, coeff defaults to 1.0


def test_regex_precompiled_per_run():
    """A second rerank with different rules must not reuse old compiled set."""
    engine = RuleEngine()
    out1 = engine.rerank([_ref("https://a.gov.cn/", 1.0)], [mk(1, r"gov", 2.0)])
    assert out1[0].final_score == 2.0
    out2 = engine.rerank([_ref("https://a.gov.cn/", 1.0)], [mk(1, r"nomatch", 9.0)])
    assert out2[0].final_score == 1.0  # different rules, no match
