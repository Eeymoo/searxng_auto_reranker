"""Unit tests for config_loader.

We use a fake PG client so tests don't need a real PostgreSQL instance.
The fake simulates: version bumps, force_reload flag, and PGUnavailable.
"""

from __future__ import annotations

import time

import pytest

from auto_reranker.config_loader import ConfigLoader
from auto_reranker.models import ConfigSnapshot, Intent, Rule
from auto_reranker.pg_client import PGUnavailable


class FakePG:
    """In-memory stand-in for PGClient.

    - `meta` controls what SELECT config_meta returns.
    - `fail_next` lets a test force the next call to raise PGUnavailable.
    """

    def __init__(self) -> None:
        self.meta: dict = {"version": 1, "force_reload": False}
        self.fail_next = False
        self.rule_rows: list[dict] = []
        self.intent_rows: list[dict] = []
        self.kw_rows: list[dict] = []
        self.cleared_force = False

    def _maybe_fail(self):
        if self.fail_next:
            self.fail_next = False
            raise PGUnavailable("simulated outage")

    def fetchone(self, sql, params=None):
        self._maybe_fail()
        if "config_meta" in sql:
            return dict(self.meta)
        return None

    def fetchall(self, sql, params=None):
        self._maybe_fail()
        if "FROM rules" in sql:
            return list(self.rule_rows)
        if "FROM intents" in sql:
            return list(self.intent_rows)
        if "intent_keywords" in sql:
            return list(self.kw_rows)
        return []

    def execute(self, sql, params=None):
        self._maybe_fail()
        if "force_reload = FALSE" in sql:
            self.cleared_force = True
            self.meta["force_reload"] = False


# --------------------------------------------------------------------------- #
# fixtures
# --------------------------------------------------------------------------- #
def _seed(pg: FakePG) -> None:
    pg.rule_rows = [
        {"id": 1, "pattern": r".*\.gov\.cn/.*", "coefficient": 2.0, "priority": 10,
         "intent_id": None, "enabled": True, "description": None},
        {"id": 2, "pattern": r".*spam\.example/.*", "coefficient": 0.0, "priority": 20,
         "intent_id": None, "enabled": True, "description": "blacklist"},
    ]
    pg.intent_rows = [
        {"id": 5, "name": "gaming", "priority": 10, "enabled": True},
    ]
    pg.kw_rows = [
        {"intent_id": 5, "keyword": "Game"},
    ]


# --------------------------------------------------------------------------- #
# tests
# --------------------------------------------------------------------------- #
def test_ttl_hit_returns_cache_without_db_call():
    pg = FakePG()
    _seed(pg)
    loader = ConfigLoader(pg, ttl_seconds=60)

    first = loader.get()
    assert first.version == 1
    assert len(first.rules) == 2

    # mutate underlying seed; because TTL not expired we should NOT see it
    pg.rule_rows.append(
        {"id": 9, "pattern": "x", "coefficient": 1.0, "priority": 99,
         "intent_id": None, "enabled": True, "description": None}
    )
    second = loader.get()
    assert len(second.rules) == 2  # cache hit, no new rule


def test_ttl_expired_repulls_when_version_changed():
    pg = FakePG()
    _seed(pg)
    loader = ConfigLoader(pg, ttl_seconds=0)  # always expired

    loader.get()
    # bump version and add a rule
    pg.meta["version"] = 2
    pg.rule_rows.append(
        {"id": 9, "pattern": "x", "coefficient": 1.0, "priority": 99,
         "intent_id": None, "enabled": True, "description": None}
    )
    snap = loader.get()
    assert snap.version == 2
    assert len(snap.rules) == 3


def test_version_unchanged_skips_full_pull():
    pg = FakePG()
    _seed(pg)
    loader = ConfigLoader(pg, ttl_seconds=0)  # always expired

    first = loader.get()
    calls_before = len(pg.rule_rows)  # snapshot current ruleset
    # Bump rule_rows in memory so a *full pull* would return more rules.
    # If the loader honours the unchanged version, it must NOT re-pull.
    pg.rule_rows.append(
        {"id": 99, "pattern": "should-not-appear", "coefficient": 1.0, "priority": 1,
         "intent_id": None, "enabled": True, "description": None}
    )
    second = loader.get()
    assert len(second.rules) == len(first.rules)  # no new rule seen -> skipped pull
    assert len(pg.rule_rows) == calls_before + 1  # mutation indeed happened on fake
    assert all(r.rule_id != 99 for r in second.rules)


def test_force_reload_triggers_full_pull_even_if_version_same():
    pg = FakePG()
    _seed(pg)
    loader = ConfigLoader(pg, ttl_seconds=60)

    first = loader.get()
    assert len(first.rules) == 2
    # Same version but force_reload flag set; rules changed on disk.
    pg.meta["force_reload"] = True
    pg.rule_rows.append(
        {"id": 9, "pattern": "x", "coefficient": 1.0, "priority": 99,
         "intent_id": None, "enabled": True, "description": None}
    )
    loader.force_next_refresh()
    second = loader.get()
    assert len(second.rules) == 3
    assert pg.cleared_force is True  # flag consumed


def test_pg_unavailable_keeps_last_cache():
    pg = FakePG()
    _seed(pg)
    loader = ConfigLoader(pg, ttl_seconds=60)

    first = loader.get()
    assert first.version == 1
    # simulate outage on next refresh window
    pg.fail_next = True
    loader.force_next_refresh()
    second = loader.get()
    # Should have fallen back to cached snapshot
    assert second.version == 1
    assert second is first  # exact cached object reused


def test_pg_unavailable_and_no_cache_returns_empty_snapshot():
    pg = FakePG()
    _seed(pg)
    loader = ConfigLoader(pg, ttl_seconds=60)
    pg.fail_next = True  # first-ever refresh fails
    snap = loader.get()
    assert isinstance(snap, ConfigSnapshot)
    assert snap.rules == []
    assert snap.intents == []


def test_intent_keywords_lowercased():
    pg = FakePG()
    _seed(pg)
    loader = ConfigLoader(pg, ttl_seconds=60)
    snap = loader.get()
    intent = snap.intents[0]
    assert intent.keywords == ("game",)  # stored lowercased for matching


def test_force_reload_bypasses_ttl_window():
    """Spec: 立即刷新 must take effect on the next search, not after TTL.

    Regression for B1: the old code short-circuited on TTL before checking
    force_reload, so a click was ignored for up to 30s.
    """
    pg = FakePG()
    _seed(pg)
    loader = ConfigLoader(pg, ttl_seconds=60)
    first = loader.get()
    assert len(first.rules) == 2

    # TTL has NOT expired (60s window), but operator clicked 立即刷新.
    pg.meta["force_reload"] = True
    # Underlying data changed (would only be visible after a full pull).
    pg.rule_rows.append(
        {"id": 99, "pattern": "new-rule", "coefficient": 1.0, "priority": 1,
         "intent_id": None, "enabled": True, "description": None}
    )
    second = loader.get()
    assert len(second.rules) == 3, "force_reload must bypass TTL"
    assert any(r.rule_id == 99 for r in second.rules)
    assert pg.cleared_force is True  # flag consumed
