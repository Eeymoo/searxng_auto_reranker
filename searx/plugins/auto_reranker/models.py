"""Configuration data transfer objects.

These are simple value objects describing the in-memory snapshot loaded from
PostgreSQL. Keeping them in one place lets every engine (rule, intent, vector)
share the same shape.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Rule:
    rule_id: int
    pattern: str
    coefficient: float
    priority: int
    intent_id: int | None  # None = generic rule (applies to all queries)
    enabled: bool
    description: str | None


@dataclass(frozen=True)
class Intent:
    intent_id: int
    name: str
    priority: int
    enabled: bool
    keywords: tuple[str, ...] = ()  # lower-cased for case-insensitive matching


@dataclass
class ConfigSnapshot:
    """Immutable-ish snapshot of the full configuration."""

    rules: list[Rule] = field(default_factory=list)
    intents: list[Intent] = field(default_factory=list)
    version: int = 0
    force_reload: bool = False

    def generic_rules(self) -> list[Rule]:
        """Rules that apply to every query (intent_id IS NULL)."""
        return [r for r in self.rules if r.intent_id is None and r.enabled]

    def intent_rules(self, intent_id: int) -> list[Rule]:
        return [r for r in self.rules if r.intent_id == intent_id and r.enabled]

    def enabled_intents(self) -> list[Intent]:
        return [i for i in self.intents if i.enabled]
