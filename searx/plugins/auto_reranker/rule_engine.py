"""Rule-based re-ranker.

Iterates rules in priority order; for each result URL, the first matching
enabled rule's coefficient is applied (`final_score = native_score * coeff`).
A coefficient of 0 removes the result entirely (blacklist).
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Iterable

from .models import Rule

logger = logging.getLogger("searx.plugins.auto_reranker.rule_engine")


@dataclass
class ResultRef:
    """Minimal view of a SearXNG result used by the re-ranker.

    Engines attach this metadata onto each result dict; the plugin orchestrator
    is responsible for projecting real results into this shape.
    """

    url: str
    score: float  # native SearXNG score
    text: str = ""  # semantic text (title + content) used by the vector reranker


@dataclass
class ScoredResult:
    url: str
    native_score: float
    final_score: float
    matched_rule_id: int | None
    dropped: bool = False
    text: str = ""  # carried through for the vector reranker


class _CompiledRules:
    """Pre-compiled rule set for a single rerun."""

    def __init__(self, rules: Iterable[Rule]) -> None:
        # Only enabled rules participate; disabled ones are skipped entirely.
        enabled_rules = [r for r in rules if r.enabled]
        ordered = sorted(enabled_rules, key=lambda r: (r.priority, r.rule_id))
        self._entries = [
            (r.rule_id, re.compile(r.pattern), r.coefficient) for r in ordered
        ]

    def match(self, url: str) -> tuple[int | None, float]:
        for rule_id, regex, coeff in self._entries:
            if regex.search(url):
                return rule_id, coeff
        return None, 1.0


class RuleEngine:
    """Applies rules and returns a re-ranked, blacklist-filtered list."""

    def rerank(
        self,
        results: list[ResultRef],
        rules: Iterable[Rule],
    ) -> list[ScoredResult]:
        compiled = _CompiledRules(rules)
        scored: list[ScoredResult] = []
        for r in results:
            rule_id, coeff = compiled.match(r.url)
            final = r.score * coeff
            dropped = coeff == 0.0
            scored.append(
                ScoredResult(
                    url=r.url,
                    native_score=r.score,
                    final_score=final,
                    matched_rule_id=rule_id,
                    dropped=dropped,
                    text=r.text,
                )
            )
        # Drop blacklisted (coefficient 0) results.
        kept = [s for s in scored if not s.dropped]
        # Stable sort: final_score desc, tie-break native_score desc, then original order.
        kept.sort(key=lambda s: (-s.final_score, -s.native_score))
        return kept
