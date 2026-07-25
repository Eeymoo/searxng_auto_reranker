"""Intent router: maps a query to zero or one effective intent via keyword match."""

from __future__ import annotations

import logging
from typing import Iterable, Optional

from .models import ConfigSnapshot, Intent

logger = logging.getLogger("searx.plugins.auto_reranker.intent_router")


class IntentRouter:
    """Selects at most one intent for a query.

    Matching is case-insensitive substring containment on any of an intent's
    keywords. When multiple intents match, the one with the lowest `priority`
    value wins (priority is a sort key, lower = higher precedence).
    """

    def select(self, query: str, snapshot: ConfigSnapshot) -> Optional[Intent]:
        if not query:
            return None
        q = query.lower()
        hits: list[Intent] = [
            i for i in snapshot.enabled_intents() if any(kw in q for kw in i.keywords)
        ]
        if not hits:
            return None
        hits.sort(key=lambda i: (i.priority, i.intent_id))
        return hits[0]

    def effective_rules(self, query: str, snapshot: ConfigSnapshot) -> list:
        """Return generic rules + (if matched) the winning intent's rules."""
        from .models import Rule

        generic = snapshot.generic_rules()
        intent = self.select(query, snapshot)
        if intent is None:
            return generic
        intent_rules: Iterable[Rule] = snapshot.intent_rules(intent.intent_id)
        # Merge; RuleEngine re-sorts globally by (priority, id).
        return [*generic, *intent_rules]
