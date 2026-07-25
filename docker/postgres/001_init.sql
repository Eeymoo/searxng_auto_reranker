-- SearXNG Auto Reranker - initial schema.
-- Apply with: psql "$DATABASE_URL" -f migrations/001_init.sql

BEGIN;

-- ------------------------------------------------------------------ --
-- intents
-- ------------------------------------------------------------------ --
CREATE TABLE IF NOT EXISTS intents (
    id          SERIAL PRIMARY KEY,
    name        VARCHAR(64) NOT NULL UNIQUE,
    description TEXT,
    priority    INT     NOT NULL DEFAULT 100,
    enabled     BOOLEAN NOT NULL DEFAULT TRUE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ------------------------------------------------------------------ --
-- intent_keywords (one-to-many)
-- ------------------------------------------------------------------ --
CREATE TABLE IF NOT EXISTS intent_keywords (
    id          SERIAL PRIMARY KEY,
    intent_id   INT NOT NULL REFERENCES intents(id) ON DELETE CASCADE,
    keyword     VARCHAR(64) NOT NULL,
    UNIQUE (intent_id, keyword)
);

-- ------------------------------------------------------------------ --
-- rules
--   * intent_id NULL  -> generic rule (applies to all queries)
--   * intent_id set   -> applies only when that intent is matched
--   * coefficient = 0 -> blacklist drop (no separate blacklist table)
-- ------------------------------------------------------------------ --
CREATE TABLE IF NOT EXISTS rules (
    id           SERIAL PRIMARY KEY,
    pattern      TEXT NOT NULL,
    coefficient  NUMERIC(4,2) NOT NULL CHECK (coefficient BETWEEN 0.0 AND 10.0),
    priority     INT     NOT NULL DEFAULT 100,
    intent_id    INT     REFERENCES intents(id) ON DELETE SET NULL,
    enabled      BOOLEAN NOT NULL DEFAULT TRUE,
    description  TEXT,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_rules_enabled_priority ON rules (enabled, priority);
CREATE INDEX IF NOT EXISTS idx_rules_intent_id        ON rules (intent_id);

-- ------------------------------------------------------------------ --
-- config_meta (single-row; id fixed to 1)
-- ------------------------------------------------------------------ --
CREATE TABLE IF NOT EXISTS config_meta (
    id            INT PRIMARY KEY DEFAULT 1,
    version       BIGINT NOT NULL DEFAULT 1,
    force_reload  BOOLEAN NOT NULL DEFAULT FALSE,
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT config_meta_singleton CHECK (id = 1)
);
INSERT INTO config_meta (id, version, force_reload)
VALUES (1, 1, FALSE)
ON CONFLICT (id) DO NOTHING;

-- ------------------------------------------------------------------ --
-- updated_at auto-bump trigger (applies to any CUD on rules/intents/keywords)
-- ------------------------------------------------------------------ --
CREATE OR REPLACE FUNCTION bump_config_meta() RETURNS TRIGGER AS $$
BEGIN
    UPDATE config_meta
       SET version = version + 1,
           updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS rules_bump_meta            ON rules;
CREATE TRIGGER rules_bump_meta            AFTER INSERT OR UPDATE OR DELETE ON rules
    FOR EACH ROW EXECUTE FUNCTION bump_config_meta();

DROP TRIGGER IF EXISTS intents_bump_meta          ON intents;
CREATE TRIGGER intents_bump_meta          AFTER INSERT OR UPDATE OR DELETE ON intents
    FOR EACH ROW EXECUTE FUNCTION bump_config_meta();

DROP TRIGGER IF EXISTS intent_keywords_bump_meta  ON intent_keywords;
CREATE TRIGGER intent_keywords_bump_meta  AFTER INSERT OR UPDATE OR DELETE ON intent_keywords
    FOR EACH ROW EXECUTE FUNCTION bump_config_meta();

COMMIT;
