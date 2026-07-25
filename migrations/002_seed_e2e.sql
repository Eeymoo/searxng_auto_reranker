-- Seed data for end-to-end verification: gaming / news / law scenarios + blacklist.

BEGIN;

-- ---------- intents ---------- --
INSERT INTO intents (name, description, priority, enabled) VALUES
  ('gaming',       '游戏类查询', 10, TRUE),
  ('programming',  '编程类查询', 20, TRUE),
  ('law',          '法律法规查询', 15, TRUE)
ON CONFLICT (name) DO NOTHING;

-- ---------- intent keywords ---------- --
INSERT INTO intent_keywords (intent_id, keyword)
SELECT i.id, kw FROM intents i
JOIN (VALUES
  ('gaming', '游戏'), ('gaming', 'steam'), ('gaming', '购买'), ('gaming', '折扣'),
  ('programming', '编程'), ('programming', 'api'), ('programming', '文档'), ('programming', 'tutorial'),
  ('law', '法条'), ('law', '法律'), ('law', '法规'), ('law', '刑法'), ('law', '民法典')
) AS v(name, kw) ON v.name = i.name
ON CONFLICT DO NOTHING;

-- ---------- generic (intent_id NULL) rules ---------- --
INSERT INTO rules (pattern, coefficient, priority, intent_id, enabled, description) VALUES
  -- 新闻 / 官方权威源
  ('.*\.gov\.cn/.*',                3.0, 10, NULL, TRUE, '政府官网加权'),
  ('.*\.people\.com\.cn/.*',        2.0, 20, NULL, TRUE, '人民网'),
  ('.*\.xinhuanet\.com/.*',         2.0, 20, NULL, TRUE, '新华网'),
  ('.*\.cctv\.com/.*',              2.0, 20, NULL, TRUE, '央视'),
  -- 黑名单 (coefficient = 0)
  ('.*spam-content-farm\.example/.*', 0, 100, NULL, TRUE, '内容农场黑名单'),
  ('.*aggregator-\d+\.example/.*',    0, 100, NULL, TRUE, '聚合站黑名单')
ON CONFLICT DO NOTHING;

-- ---------- gaming-intent rules ---------- --
INSERT INTO rules (pattern, coefficient, priority, intent_id, enabled, description)
SELECT pat, coeff, prio, i.id, TRUE, descr FROM intents i
JOIN (VALUES
  ('gaming', '.*store\.steampowered\.com/.*', 5.0, 30, 'Steam 商店'),
  ('gaming', '.*\.epicgames\.com/.*',         3.0, 40, 'Epic Games'),
  ('gaming', '.*\.gog\.com/.*',               3.0, 40, 'GOG')
) AS v(name, pat, coeff, prio, descr) ON v.name = i.name
ON CONFLICT DO NOTHING;

-- ---------- law-intent rules ---------- --
-- NOTE: 法条专属规则的 priority 必须 < 通用 *.gov.cn 规则 (priority 10),
-- 否则通用政府规则会先命中并把法条源压成普通政府系数。
-- pattern 也用更窄的域名(flk.npc.gov.cn)以便精确匹配。
INSERT INTO rules (pattern, coefficient, priority, intent_id, enabled, description)
SELECT pat, coeff, prio, i.id, TRUE, descr FROM intents i
JOIN (VALUES
  ('law', '.*flk\.npc\.gov\.cn/.*',           5.0, 5,  '国家法律法规数据库(优先级<通用gov)'),
  ('law', '.*\.pkulaw\.com/.*',               5.0, 5,  '北大法宝'),
  ('law', '.*\.chinacourt\.org/.*',           3.0, 6,  '中国法院网')
) AS v(name, pat, coeff, prio, descr) ON v.name = i.name
ON CONFLICT DO NOTHING;

COMMIT;

-- ---------- verify seed ---------- --
SELECT 'intents' AS what, COUNT(*)::text AS n FROM intents
UNION ALL SELECT 'keywords',  COUNT(*)::text FROM intent_keywords
UNION ALL SELECT 'rules_total', COUNT(*)::text FROM rules
UNION ALL SELECT 'rules_blacklist', COUNT(*)::text FROM rules WHERE coefficient = 0;
