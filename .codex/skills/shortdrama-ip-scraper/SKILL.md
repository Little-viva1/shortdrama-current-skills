---
name: shortdrama-ip-scraper
description: Batch scrape IP application/list data from creator.shortdramas.com copyright IP pages and export complete IP records as CSV/XLSX tables. Use when the user asks to fetch all IPs, crawl the IP榜单/IP申请 list, export IP metadata such as title, category tags, author, score, pick/apply counts, completion status, word count, reader count, or build a reusable shortdrama IP information table from curl/cookie captures.
---

# Shortdrama IP Scraper

## Overview

Use this skill to turn the copyright IP list API into a repeatable table export. Prefer the bundled script over rewriting ad hoc requests.

Core script:

```powershell
python .codex\skills\shortdrama-ip-scraper\scripts\fetch_shortdrama_ips.py --help
```

## Inputs

Provide authentication in one of these ways:

- `--cookie "k=v; k2=v2"` for a raw browser Cookie header.
- `--curl-python docs\未归档\curl转python\IP申请.txt` to parse the `cookies = {...}` dict from a curl-to-Python capture.
- Environment variable `SHORTDRAMA_COOKIE`.

Do not hard-code cookies into the skill or commit exported private cookies.

## Default Workflow

1. Verify the source is the IP application page/API, not static resources or monitoring posts.
2. Run a small smoke test with `--max-pages 1 --format csv` to confirm the session is valid.
3. Run the full export with conservative pacing.
4. Check the final row count and inspect the `raw_json` column if a requested field is not mapped into a friendly column.

Example:

```powershell
python .codex\skills\shortdrama-ip-scraper\scripts\fetch_shortdrama_ips.py `
  --curl-python docs\未归档\curl转python\IP申请.txt `
  --output data\shortdrama-ip\ip_export.csv `
  --format csv
```

For XLSX, install `openpyxl` if needed, then use `--format xlsx` or `--format both`.

## API Notes

Known endpoints from captures:

- `GET https://creator.shortdramas.com/api/playlet/ip/list/v1`
- `GET https://creator.shortdramas.com/api/playlet/category/list/v1?genre=15`

Known list parameters:

- Pagination: `page_index`, `page_size`
- Defaults: `image_fmt=90x120`, `ip_source=1`, `ip_apply_type=3`
- Observed filters: `gender`, `word_num_gt`, `word_num_lt`

Use `--extra-param key=value` for newly observed filters without editing the script.

## Output

The script exports stable friendly columns first, then flattened API fields:

- `ip_id`
- `作品名`
- `类目分类tag`
- `作者`
- `评分`
- `挑选次数`
- `完结状态`
- `字数`
- `读者数`
- all flattened scalar fields discovered in the API response
- `raw_json`

If a field name changes, keep the full row because `raw_json` preserves the source record.

## Reliability Rules

- Use `--sleep 0.6` or slower for full exports.
- Avoid enumerating every filter combination unless the user explicitly needs platform-filtered result sets; a full crawl plus local filtering is usually faster and less noisy.
- Stop and ask for a fresh login/cookie if the response is HTML, 401/403, or contains an obvious login challenge.
- Deduplicate by discovered IP ID fields, falling back to title when no ID is present.
