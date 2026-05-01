# API Observations

Observed from `docs/未归档/curl转python/IP申请.txt`.

## List Endpoint

`GET https://creator.shortdramas.com/api/playlet/ip/list/v1`

Common params:

- `page_index=1`
- `page_size=20`
- `image_fmt=90x120`
- `ip_source=1`
- `ip_apply_type=3`

Observed filters:

- `gender=0`
- `gender=1`
- `word_num_gt=30000`
- `word_num_lt=50000`

Observed browser timings were roughly 0.5-0.7 seconds per page for 20 rows.

## Category Endpoint

`GET https://creator.shortdramas.com/api/playlet/category/list/v1?genre=15`

Use it to build a best-effort ID-to-name map for category/tag fields returned in IP records.
