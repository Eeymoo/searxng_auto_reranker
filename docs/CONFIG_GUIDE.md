# Configuration guide

This document shows practical rule sets for common Chinese search scenarios and explains how each field behaves.

## Field reference (rules table)

| Field          | Type         | Default | Notes |
| -------------- | ------------ | ------- | ----- |
| `pattern`      | TEXT         | —       | Python regex tested against the result URL. |
| `coefficient`  | NUMERIC(4,2) | —       | Multiplied with SearXNG's native score. Range `0.0` – `10.0`. `0` drops the result (blacklist). |
| `priority`     | INT          | 100     | Lower number = evaluated first. First matching rule wins; the rest are ignored for that URL. |
| `intent_id`    | INT (null)   | NULL    | NULL → generic (all queries). Set → applies only when the intent is matched. |
| `enabled`      | BOOL         | TRUE    | Disabled rules are skipped entirely. |
| `description`  | TEXT         | NULL    | Free-form note shown in the UI. |

## Scoring

```
final_score = native_score × coefficient
```

- Rules are tried in `priority ASC, id ASC` order; **the first match wins**.
- Unmatched URLs keep coefficient `1.0` (native ranking unchanged).
- Results with `coefficient == 0` are removed entirely (blacklist).
- Ties on final score break by native score (desc).

## Typical Chinese-scenario rules

### 1. Boost government / authoritative sites

| pattern                  | coefficient | priority | intent_id |
| ------------------------ | ----------- | -------- | --------- |
| `.*\.gov\.cn/.*`         | 3.0         | 10       | NULL      |
| `.*\.people\.com\.cn/.*` | 2.0         | 20       | NULL      |
| `.*\.xinhuanet\.com/.*`  | 2.0         | 20       | NULL      |

### 2. Gaming intent → boost Steam

Create an intent named `gaming` (priority 10), with keywords `游戏`, `购买`, `steam`, `折扣`. Then add a rule **attached to that intent**:

| pattern                          | coefficient | priority | intent_id |
| -------------------------------- | ----------- | -------- | --------- |
| `.*store\.steampowered\.com/.*`  | 5.0         | 30       | (id of `gaming`) |
| `.*\.epicgames\.com/.*`          | 3.0         | 40       | (id of `gaming`) |

Now `购买 赛博朋克2077` (matched on `购买`) lifts Steam above generic results, while a programming query (`rust async`) is unaffected.

### 3. Programming intent → official docs

Intent `programming` (keywords: `编程`, `api`, `文档`, `howto`, `tutorial`):

| pattern                            | coefficient | priority | intent_id        |
| ---------------------------------- | ----------- | -------- | ---------------- |
| `.*docs\.(python|rust-lang)\.org.*`| 4.0         | 30       | programming.id   |
| `.*developer\.mozilla\.org/.*`     | 3.0         | 40       | programming.id   |
| `.*stackoverflow\.com/.*`          | 2.0         | 50       | programming.id   |

### 4. Blacklist low-quality aggregators

Use the dedicated **Blacklist** page in the UI (or set `coefficient = 0` on a rule):

| pattern                       | coefficient | intent_id |
| ----------------------------- | ----------- | --------- |
| `.*spam-content-farm\.example/.*` | 0       | NULL      |
| `.*aggregator-\d+\.example/.*`    | 0       | NULL      |

These results are dropped before the vector stage, so they never appear.

## Using the Test page

Before saving, preview a rule from **Test**:

1. Enter the URL of a real result, e.g. `https://store.steampowered.com/app/1091500`.
2. (Optional) Enter the query that should match an intent, e.g. `买 steam 游戏`.
3. Hit **Test**. You'll see the winning rule, applied coefficient, and whether the URL would be dropped.

## Tuning tips

- Start with **small coefficients** (1.5–3.0); large values (8–10) will dominate native ranking and may suppress otherwise-good results.
- Use **priority** to express policy ("government always before news"): give `gov.cn` priority 10, news sites priority 20.
- Keep the blacklist **narrow** (anchored patterns) — overly broad regexes can silently remove good results.
- If you're unsure, set `enabled = false` while testing: the rule stays in the DB but has no effect.

### ⚠ Gotcha: generic rules can shadow intent rules

This was a real bug found during the Docker end-to-end run. Suppose you have:

- a *generic* rule `.*\.gov\.cn/.*` with `priority=10`, coefficient `3.0`
- a *law-intent* rule `.*flk\.npc\.gov\.cn/.*` with `priority=30`, coefficient `5.0`

Even when the query matches the `law` intent, the generic `gov.cn` rule wins for `flk.npc.gov.cn` URLs because `priority 10 < priority 30` and **first-match-wins is global across the merged generic+intent rule set**. The law source is then boosted by only 3.0 instead of the intended 5.0.

**Fix**: give specific intent rules a *lower* priority value than the generic rule they should beat. E.g. set the law-intent rule's `priority = 5` so it is evaluated before the generic `gov.cn` rule. Narrower URL patterns (`flk.npc.gov.cn` rather than just `npc.gov.cn`) help too. See [`docs/VERIFICATION.md`](./VERIFICATION.md#bugs-found-and-fixed-by-the-live-run) for the case study.
