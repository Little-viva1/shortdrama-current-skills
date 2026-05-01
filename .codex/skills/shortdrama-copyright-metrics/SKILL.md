---
name: shortdrama-copyright-metrics
description: >
  Fetch total play counts and related metrics for specific short dramas from
  creator.shortdramas.com copyright-center APIs. Use when the user provides
  curl-to-python samples, auth cookies or headers, a drama title, or a
  playlet_id and needs to list available dramas, resolve a playlet ID, fetch
  overview metrics, or compute lifetime plays from trend data such as
  server_vv. Prefer this skill over ad hoc curl rewrites when the workflow
  should be repeatable and scriptable.
---

# Shortdrama Copyright Metrics

## Overview

Use this skill to turn copyright-center API captures into a repeatable workflow
for listing playlets, resolving a target playlet, extracting total plays, and
pulling cumulative totals for all visible manga playlets in one run.
Keep login state outside the repo. Reuse the bundled script instead of
rewriting `requests` code every time.

## Core Resources

- Script: `scripts/fetch_playlet_metrics.py`
- Auth config reference: `references/auth-config.md`

## Workflow

### 1. Determine the input shape

Handle one of these inputs first:

- A playlet title
- A `playlet_id`
- A batch of `curl -> python` samples
- An existing auth JSON

If the user only provides captured requests:

- Extract `cookies`
- Extract `headers` except the raw `cookie` header
- Extract `role_type`, `author_type`, and `member_type`
- Build an external auth JSON using `references/auth-config.md`
- Do not commit real tokens or sessions into the repo

### 2. Validate the auth with the script

Typical commands:

```bash
python .codex/skills/shortdrama-copyright-metrics/scripts/fetch_playlet_metrics.py --auth path/to/auth.json list
python .codex/skills/shortdrama-copyright-metrics/scripts/fetch_playlet_metrics.py --auth path/to/auth.json total --title "Drama Title"
python .codex/skills/shortdrama-copyright-metrics/scripts/fetch_playlet_metrics.py --auth path/to/auth.json total --playlet-id 7630721610911075353
python .codex/skills/shortdrama-copyright-metrics/scripts/fetch_playlet_metrics.py --auth path/to/auth.json all-totals
python .codex/skills/shortdrama-copyright-metrics/scripts/fetch_playlet_metrics.py --auth path/to/auth.json all-completion
python .codex/skills/shortdrama-copyright-metrics/scripts/fetch_playlet_metrics.py --auth path/to/auth.json revenue-report --benchmark-title "Benchmark Drama" --benchmark-revenue 175
python .codex/skills/shortdrama-copyright-metrics/scripts/fetch_playlet_metrics.py --auth path/to/auth.json revenue-report --benchmark-title "Benchmark Drama" --benchmark-revenue 175 --settlement-start-date 20260301 --settlement-end-date 20260428
python .codex/skills/shortdrama-copyright-metrics/scripts/fetch_playlet_metrics.py --auth path/to/auth.json --output totals.csv all-totals
```

### 3. Compute total play count

Use this order:

1. Call `selected_playlet/list` to locate the target playlet and publish date
2. Call `metric/overview`
3. Call `metric/trend` with `server_vv`
4. If overview exposes a stable total-value candidate, include it as a cross-check
5. If no stable total field is exposed, use the lifetime `server_vv` trend sum as `total_play_count`

Do not assume overview field names are stable. The script already applies
heuristics, but the final answer should still say whether the total came from
`overview_candidate` or `trend_sum`.

### 4. Pull all visible manga totals

When the user wants one-click totals for every visible manga playlet:

1. Call `selected_playlet/list` to get the visible playlet IDs
2. Call `rank/list` in batches with a wide date range
3. Read the cumulative metric `listen_dcnt_td` from the rank response
4. Return one row per visible playlet

Use `all-totals` for this path. Prefer `--output totals.csv` or
`--output totals.json` when the user wants a reusable export.

### 5. Pull completion metrics and estimate watched time

When the user wants completion metrics or an estimated effective watched time:

1. Call `selected_playlet/list` to get the visible playlet IDs
2. Call `rank/list` in batches with a wide date range
3. Read completion-related metrics and series from the rank response
4. Return the raw completion indicators plus derived watched-time estimates

Use `all-completion` for this path. Treat the watched-time fields as estimates,
not platform-native metrics.

### 6. Pull a one-shot revenue report

When the user wants one command that covers totals, completion, watched-time
estimates, and benchmark-based revenue estimation:

1. Call `all-completion`
2. Select the benchmark row by title or playlet ID
3. Scale other rows from the benchmark revenue using a chosen basis
4. Return one report row per visible playlet

Use `revenue-report` for this path. Default revenue scaling should use
`duration_adjusted_effective_hours` unless the user explicitly asks for another
basis. Keep `lower_bound_effective_hours` in the output as a conservative
comparison.

When the benchmark revenue belongs to a settlement period instead of the full
cumulative play window, require `--settlement-start-date` and
`--settlement-end-date`. In that mode, revenue scaling defaults to
`settlement_duration_adjusted_effective_hours`, which uses trend `server_vv`
sums for the settlement period.

The duration-adjusted basis is:

```text
min(total_play_count * playlet_total_duration_min, max(estimated_effective_play_minutes, lower_bound_effective_minutes))
```

This makes total duration a hard cap while preserving the conservative
time-bucket lower bound.

### 7. Failure routing

- If auth fails with 401 or 403, state that the login state expired
- If the title is not found, return the visible playlet list or filtered candidates
- If the playlet is found but no publish date is exposed, require `--start-date YYYYMMDD`
- If trend succeeds but overview fails, return the trend-based result and mark it as a degraded path
- If overview succeeds but trend fails, return the overview candidate and note that trend validation is missing

## Output Rules

Always include:

- Matched title
- `playlet_id`
- Time range
- `metric_key`
- `total_play_count`
- Total source: `trend_sum` or `overview_candidate`
- Any auth or schema risk that affects confidence

For `all-totals`, include:

- Row count
- Query range
- One row per visible playlet
- The cumulative metric key and name used for extraction

Do not dump raw captures or full API bodies unless debugging is required. When
debugging is required, use `--dump-response-dir`.

## Never Do

- Never store real cookies, session IDs, or CSRF tokens in the skill files
- Never pretend the workflow can run without valid auth
- Never assume `metric/overview` always contains the final total field you want
- Never invent a time range when the publish date is missing
