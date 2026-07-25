"""Config loader: PostgreSQL -> ConfigSnapshot with TTL cache + degradation."""

from __future__ import annotations

import logging
import time
from typing import Optional

from .models import ConfigSnapshot, Intent, Rule
from .pg_client import PGClient, PGUnavailable

logger = logging.getLogger("searx.plugins.auto_reranker.config_loader")

DEFAULT_TTL = 30.0  # seconds


class ConfigLoader:
    """Caches the full configuration in-memory and refreshes it on TTL expiry.

    Degradation policy (per spec ``config-store``):
      * TTL hit          -> return cached snapshot, no DB hit
      * TTL expired      -> check meta version; re-pull only if changed
      * PG unavailable   -> keep last good snapshot; log error
      * PG unavailable AND no cache -> return empty snapshot (native ranking)
    """

    def __init__(self, pg: PGClient, ttl_seconds: float = DEFAULT_TTL) -> None:
        self._pg = pg
        self._ttl = float(ttl_seconds)
        self._cache: Optional[ConfigSnapshot] = None
        self._expires_at: float = 0.0

    # ------------------------------------------------------------------ #
    # public API
    # ------------------------------------------------------------------ #
    @property
    def ttl(self) -> float:
        return self._ttl

    def get(self) -> ConfigSnapshot:
        """Return the current effective ConfigSnapshot, refreshing if stale.

        Refresh triggers when ANY of these hold:
          * TTL has expired, OR
          * `config_meta.force_reload` is TRUE (operator clicked "Refresh now").
        The force_reload check happens BEFORE the TTL short-circuit so the
        "立即刷新" button takes effect on the next search, not after TTL.
        See spec config-admin-ui "立即刷新配置".
        """
        now = time.monotonic()
        # 1) If TTL hasn't expired AND force_reload isn't set, serve cache cheaply.
        if self._cache is not None and now < self._expires_at:
            if not self._is_force_reload_set():
                return self._cache  # cache hit
            # force_reload is set -> fall through to refresh
        refreshed = self._refresh(now)
        return refreshed if refreshed is not None else (self._cache or ConfigSnapshot())

    def force_next_refresh(self) -> None:
        """Mark cache as immediately stale (in-process; rare external use)."""
        self._expires_at = 0.0

    # ------------------------------------------------------------------ #
    def _is_force_reload_set(self) -> bool:
        """Cheap single-row probe of `config_meta.force_reload`.

        Returns False on PG failure (so a transient outage doesn't bypass
        the cache and trigger a storm of full pulls).
        """
        try:
            meta = self._pg.fetchone(
                "SELECT force_reload FROM config_meta WHERE id = 1"
            )
            return bool(meta and meta.get("force_reload", False))
        except PGUnavailable:
            return False

    # ------------------------------------------------------------------ #
    # internals
    # ------------------------------------------------------------------ #
    def _refresh(self, now: float) -> Optional[ConfigSnapshot]:
        try:
            meta = self._pg.fetchone(
                "SELECT version, force_reload FROM config_meta WHERE id = 1"
            ) or {"version": 0, "force_reload": False}
            version = int(meta.get("version", 0))
            force = bool(meta.get("force_reload", False))
            if self._cache is not None and not force and version == self._cache.version:
                # version unchanged: skip full pull, just extend TTL
                self._expires_at = now + self._ttl
                return self._cache
            snapshot = self._pull_full()
            snapshot.version = version
            snapshot.force_reload = False  # consumed locally
            # Clear the force_reload flag server-side so other instances see it.
            if force:
                try:
                    self._pg.execute(
                        "UPDATE config_meta SET force_reload = FALSE WHERE id = 1"
                    )
                except PGUnavailable:
                    logger.warning("could not clear force_reload flag")
            self._cache = snapshot
            self._expires_at = now + self._ttl
            return snapshot
        except PGUnavailable:
            if self._cache is not None:
                logger.error("PG unavailable, serving last cached config (version=%d)", self._cache.version)
            else:
                logger.error("PG unavailable and no cache: degrading to native ranking")
            # Keep any existing cache; just push expiry forward to avoid hot-looping
            self._expires_at = now + self._ttl
            return None

    def _pull_full(self) -> ConfigSnapshot:
        rule_rows = self._pg.fetchall(
            "SELECT id, pattern, coefficient, priority, intent_id, enabled, description "
            "FROM rules ORDER BY priority ASC, id ASC"
        )
        rules = [
            Rule(
                rule_id=int(r["id"]),
                pattern=r["pattern"],
                coefficient=float(r["coefficient"]),
                priority=int(r["priority"]),
                intent_id=(int(r["intent_id"]) if r["intent_id"] is not None else None),
                enabled=bool(r["enabled"]),
                description=r.get("description"),
            )
            for r in rule_rows
        ]

        intent_rows = self._pg.fetchall(
            "SELECT id, name, priority, enabled FROM intents ORDER BY priority ASC, id ASC"
        )
        # Pre-load keywords in one query to avoid N+1.
        kw_rows = self._pg.fetchall("SELECT intent_id, keyword FROM intent_keywords")
        kw_by_intent: dict[int, list[str]] = {}
        for row in kw_rows:
            kw_by_intent.setdefault(int(row["intent_id"]), []).append(str(row["keyword"]).lower())

        intents = [
            Intent(
                intent_id=int(i["id"]),
                name=str(i["name"]),
                priority=int(i["priority"]),
                enabled=bool(i["enabled"]),
                keywords=tuple(kw_by_intent.get(int(i["id"]), [])),
            )
            for i in intent_rows
        ]
        return ConfigSnapshot(rules=rules, intents=intents)
