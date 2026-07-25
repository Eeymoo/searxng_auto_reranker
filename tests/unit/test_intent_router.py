"""Unit tests for intent_router."""

from __future__ import annotations

from auto_reranker.intent_router import IntentRouter
from auto_reranker.models import ConfigSnapshot, Intent, Rule


def _intent(iid, name, priority, keywords, enabled=True):
    return Intent(
        intent_id=iid,
        name=name,
        priority=priority,
        enabled=enabled,
        keywords=tuple(k.lower() for k in keywords),
    )


def _rule(rule_id, intent_id=None, pattern=r".*", coeff=1.0, priority=100):
    return Rule(
        rule_id=rule_id,
        pattern=pattern,
        coefficient=coeff,
        priority=priority,
        intent_id=intent_id,
        enabled=True,
        description=None,
    )


def test_single_intent_matched_by_keyword_substring():
    router = IntentRouter()
    snap = ConfigSnapshot(
        intents=[_intent(5, "gaming", 10, ["游戏", "steam"])],
    )
    selected = router.select("赛博朋克2077 购买 游戏", snap)
    assert selected is not None
    assert selected.intent_id == 5


def test_case_insensitive_match():
    router = IntentRouter()
    snap = ConfigSnapshot(intents=[_intent(1, "news", 10, ["STEAM"])])
    assert router.select("i love steam decks", snap) is not None


def test_no_intent_matched_returns_none():
    router = IntentRouter()
    snap = ConfigSnapshot(
        intents=[_intent(5, "gaming", 10, ["游戏"])],
    )
    assert router.select("如何做番茄炒蛋", snap) is None


def test_multiple_intents_lower_priority_value_wins():
    router = IntentRouter()
    snap = ConfigSnapshot(
        intents=[
            _intent(1, "gaming", priority=10, keywords=["折扣"]),
            _intent(2, "programming", priority=20, keywords=["折扣"]),  # same kw
        ]
    )
    selected = router.select("steam 折扣", snap)
    assert selected.intent_id == 1  # priority 10 wins


def test_disabled_intent_does_not_match():
    router = IntentRouter()
    snap = ConfigSnapshot(
        intents=[_intent(5, "gaming", 10, ["游戏"], enabled=False)],
    )
    assert router.select("买新游戏", snap) is None


def test_effective_rules_merges_generic_and_intent_rules():
    router = IntentRouter()
    generic = _rule(1, intent_id=None, pattern=r".*\.gov\.cn/.*", coeff=2.0, priority=10)
    intent_only = _rule(2, intent_id=5, pattern=r".*steampowered\.com/.*", coeff=3.0, priority=20)
    unrelated = _rule(3, intent_id=99, pattern=r".*github\.com/.*", coeff=2.0, priority=20)
    snap = ConfigSnapshot(
        rules=[generic, intent_only, unrelated],
        intents=[_intent(5, "gaming", 10, ["steam"])],
    )
    effective = router.effective_rules("购买 steam 游戏", snap)
    ids = {r.rule_id for r in effective}
    assert ids == {1, 2}  # generic + matched intent only; unrelated intent excluded


def test_effective_rules_generic_only_when_no_intent():
    router = IntentRouter()
    generic = _rule(1, intent_id=None, coeff=2.0)
    intent_only = _rule(2, intent_id=5, coeff=3.0)
    snap = ConfigSnapshot(
        rules=[generic, intent_only],
        intents=[_intent(5, "gaming", 10, ["steam"])],
    )
    effective = router.effective_rules("做番茄炒蛋", snap)  # no intent matched
    assert {r.rule_id for r in effective} == {1}


def test_empty_query_returns_none():
    router = IntentRouter()
    snap = ConfigSnapshot(intents=[_intent(1, "x", 10, ["a"])])
    assert router.select("", snap) is None
