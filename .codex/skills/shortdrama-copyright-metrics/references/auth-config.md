# Auth Config

This skill expects an external auth JSON. Do not commit real credentials into
the repo.

## Minimum Structure

```json
{
  "cookies": {
    "sessionid": "...",
    "sessionid_ss": "...",
    "sid_tt": "...",
    "passport_csrf_token": "...",
    "passport_csrf_token_default": "..."
  },
  "headers": {
    "accept": "application/json, text/plain, */*",
    "content-type": "application/json",
    "origin": "https://creator.shortdramas.com",
    "referer": "https://creator.shortdramas.com/page/copyright/data-center-fanqie",
    "user-agent": "Mozilla/5.0 ..."
  },
  "api_params": {
    "role_type": "3",
    "author_type": "1",
    "member_type": "3"
  },
  "filters": {
    "playlet_source": 1,
    "genre": 15,
    "playlet_type": 1,
    "data_source": 2
  },
  "ttwid_payload": {
    "aid": 791322,
    "service": "creator.shortdramas.com",
    "unionHost": "",
    "union": false,
    "needFid": false,
    "fid": "",
    "migrate_priority": 0
  }
}
```

## Extraction Rules

- `cookies`: copy the `cookies = {...}` mapping from the captured sample
- `headers`: copy the request headers except the raw `cookie` header
- `api_params`: keep the fixed query params such as `role_type`, `author_type`, and `member_type`
- `filters`: keep the captured `playlet_source`, `genre`, `playlet_type`, and `data_source`
- `ttwid_payload`: if the capture includes `/ttwid/check/`, copy the associated JSON payload

## Recommendations

- Refresh the auth JSON whenever login state expires
- Keep auth JSON outside the skill folder unless the user explicitly wants a local private copy
- Use `--dump-response-dir` when debugging schema differences between accounts or dates
- The same auth JSON works for `list`, `total`, and `all-totals`
