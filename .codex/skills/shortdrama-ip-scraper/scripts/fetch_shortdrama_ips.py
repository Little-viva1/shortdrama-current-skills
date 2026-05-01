#!/usr/bin/env python3
"""Export creator.shortdramas.com copyright IP list records to CSV/XLSX."""

from __future__ import annotations

import argparse
import ast
import csv
import json
import os
import re
import sys
import time
from collections import OrderedDict
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl

import requests


LIST_URL = "https://creator.shortdramas.com/api/playlet/ip/list/v1"
CATEGORY_URL = "https://creator.shortdramas.com/api/playlet/category/list/v1"

FRIENDLY_COLUMNS = [
    "ip_id",
    "作品名",
    "类目分类tag",
    "作者",
    "评分",
    "挑选次数",
    "完结状态",
    "字数",
    "读者数",
]

TITLE_KEYS = ["title", "name", "book_name", "ip_name", "playlet_name", "novel_name", "work_name"]
ID_KEYS = ["ip_id", "id", "book_id", "novel_id", "item_id", "playlet_id"]
AUTHOR_KEYS = ["author", "author_name", "writer", "writer_name", "pen_name"]
SCORE_KEYS = ["score", "book_score", "rate", "rating", "grade", "recommend_score", "hot_score"]
PICK_KEYS = ["pick_count", "ip_selected_count", "select_count", "selected_count", "apply_count", "choice_count", "choose_count"]
STATUS_KEYS = ["finish_status", "creation_status", "complete_status", "completion_status", "serialize_status", "status"]
WORD_KEYS = ["word_num", "word_count", "words", "book_word_num"]
READER_KEYS = ["reader_count", "read_listen_dcnt_14d", "read_count", "readers", "reading_user_count", "follow_count"]
TAG_KEYS = ["tags", "tag_list", "category", "category_list", "category_ids", "category_id", "genre", "genre_list"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cookie", help="Raw Cookie header string.")
    parser.add_argument("--curl-python", help="curl-to-Python file containing a cookies = {...} dict.")
    parser.add_argument("--output", default="data/shortdrama-ip/ip_export.csv", help="Output path.")
    parser.add_argument("--format", choices=["csv", "xlsx", "both"], default="csv", help="Export format.")
    parser.add_argument("--page-size", type=int, default=100, help="Rows per page to request.")
    parser.add_argument("--max-pages", type=int, help="Stop after N pages for smoke tests.")
    parser.add_argument("--sleep", type=float, default=0.6, help="Delay between list requests in seconds.")
    parser.add_argument("--timeout", type=float, default=20.0, help="HTTP timeout in seconds.")
    parser.add_argument("--filter-gender", choices=["0", "1"], help="Optional gender filter.")
    parser.add_argument("--word-num-gt", help="Optional lower word-count bound.")
    parser.add_argument("--word-num-lt", help="Optional upper word-count bound.")
    parser.add_argument(
        "--extra-param",
        action="append",
        default=[],
        help="Additional list query parameter as key=value. Can be repeated.",
    )
    parser.add_argument("--no-categories", action="store_true", help="Skip category/tag lookup.")
    parser.add_argument("--include-raw", action="store_true", default=True, help="Include raw_json column.")
    return parser.parse_args()


def cookies_from_header(header: str) -> dict[str, str]:
    return {k.strip(): v.strip() for k, v in parse_qsl(header.replace("; ", "&"), keep_blank_values=True)}


def cookies_from_curl_python(path: str) -> dict[str, str]:
    text = Path(path).read_text(encoding="utf-8")
    match = re.search(r"cookies\s*=\s*(\{.*?\})\s*\n", text, flags=re.S)
    if not match:
        raise ValueError(f"No cookies dict found in {path}")
    value = ast.literal_eval(match.group(1))
    if not isinstance(value, dict):
        raise ValueError(f"cookies value in {path} is not a dict")
    return {str(k): str(v) for k, v in value.items()}


def resolve_cookies(args: argparse.Namespace) -> dict[str, str]:
    if args.cookie:
        return cookies_from_header(args.cookie)
    env_cookie = os.environ.get("SHORTDRAMA_COOKIE")
    if env_cookie:
        return cookies_from_header(env_cookie)
    if args.curl_python:
        return cookies_from_curl_python(args.curl_python)
    raise SystemExit("Provide --cookie, --curl-python, or SHORTDRAMA_COOKIE.")


def request_json(session: requests.Session, url: str, params: dict[str, Any], timeout: float) -> Any:
    response = session.get(url, params=params, timeout=timeout)
    content_type = response.headers.get("content-type", "")
    if response.status_code in {401, 403}:
        raise RuntimeError(f"Auth failed with HTTP {response.status_code}; refresh login cookies.")
    response.raise_for_status()
    if "json" not in content_type:
        sample = response.text[:120].replace("\n", " ")
        raise RuntimeError(f"Expected JSON but got {content_type!r}: {sample}")
    return response.json()


def iter_dicts(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    return []


def find_records(payload: Any) -> list[dict[str, Any]]:
    candidates: list[tuple[int, list[dict[str, Any]]]] = []

    def walk(value: Any, key_hint: str = "") -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                if isinstance(child, list):
                    dicts = iter_dicts(child)
                    if dicts:
                        score = 2 if key in {"list", "items", "data", "records", "ip_list"} else 1
                        candidates.append((score, dicts))
                walk(child, key)
        elif isinstance(value, list):
            for child in value:
                walk(child, key_hint)

    walk(payload)
    if not candidates and isinstance(payload, list):
        return iter_dicts(payload)
    if not candidates:
        return []
    return max(candidates, key=lambda item: (item[0], len(item[1])))[1]


def flatten(value: Any, prefix: str = "") -> OrderedDict[str, Any]:
    row: OrderedDict[str, Any] = OrderedDict()
    if isinstance(value, dict):
        for key, child in value.items():
            next_prefix = f"{prefix}.{key}" if prefix else str(key)
            row.update(flatten(child, next_prefix))
    elif isinstance(value, list):
        if all(not isinstance(item, (dict, list)) for item in value):
            row[prefix] = "|".join("" if item is None else str(item) for item in value)
        else:
            row[prefix] = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    else:
        row[prefix] = value
    return row


def first_value(record: dict[str, Any], keys: list[str]) -> Any:
    flat = flatten(record)
    lowered = {key.lower().split(".")[-1]: value for key, value in flat.items()}
    for key in keys:
        if key in record and record[key] not in (None, ""):
            return record[key]
        value = lowered.get(key.lower())
        if value not in (None, ""):
            return value
    return ""


def normalize_status(value: Any) -> str:
    mapping = {
        "0": "连载中",
        "1": "已完结",
        "2": "已完结",
        "3": "已完结",
        "serializing": "连载中",
        "finished": "已完结",
        "complete": "已完结",
    }
    text = str(value) if value not in (None, "") else ""
    return mapping.get(text.lower(), text)


def collect_category_names(value: Any, category_map: dict[str, str]) -> list[str]:
    names: list[str] = []
    if value in (None, ""):
        return names
    if isinstance(value, dict):
        for key in ["name", "title", "category_name", "tag_name"]:
            if value.get(key):
                names.append(str(value[key]))
        for key in ["id", "category_id", "tag_id"]:
            if value.get(key) is not None:
                mapped = category_map.get(str(value[key]))
                if mapped:
                    names.append(mapped)
        for child in value.values():
            names.extend(collect_category_names(child, category_map))
    elif isinstance(value, list):
        for item in value:
            names.extend(collect_category_names(item, category_map))
    else:
        for part in str(value).split("|"):
            part = part.strip()
            names.append(category_map.get(part, part))
    return names


def friendly_row(record: dict[str, Any], category_map: dict[str, str]) -> OrderedDict[str, Any]:
    flat = flatten(record)
    tag_values = []
    for key, value in record.items():
        if key in TAG_KEYS or key.lower() in TAG_KEYS:
            tag_values.extend(collect_category_names(value, category_map))
    for key, value in flat.items():
        if key.lower().split(".")[-1] in TAG_KEYS:
            tag_values.extend(collect_category_names(value, category_map))
    unique_tags = list(OrderedDict.fromkeys(item for item in tag_values if item))

    row: OrderedDict[str, Any] = OrderedDict()
    row["ip_id"] = first_value(record, ID_KEYS)
    row["作品名"] = first_value(record, TITLE_KEYS)
    row["类目分类tag"] = "|".join(unique_tags)
    row["作者"] = first_value(record, AUTHOR_KEYS)
    row["评分"] = first_value(record, SCORE_KEYS)
    row["挑选次数"] = first_value(record, PICK_KEYS)
    row["完结状态"] = normalize_status(first_value(record, STATUS_KEYS))
    row["字数"] = first_value(record, WORD_KEYS)
    row["读者数"] = first_value(record, READER_KEYS)
    return row


def update_category_map(category_map: dict[str, str], value: Any) -> None:
    if isinstance(value, dict):
        item_id = None
        item_name = None
        for key in ["id", "category_id", "tag_id", "value"]:
            if value.get(key) is not None:
                item_id = str(value[key])
                break
        for key in ["name", "category_name", "tag_name", "label", "title"]:
            if value.get(key):
                item_name = str(value[key])
                break
        if item_id and item_name:
            category_map[item_id] = item_name
        for child in value.values():
            update_category_map(category_map, child)
    elif isinstance(value, list):
        for child in value:
            update_category_map(category_map, child)


def fetch_categories(session: requests.Session, timeout: float) -> dict[str, str]:
    category_map: dict[str, str] = {}
    try:
        payload = request_json(session, CATEGORY_URL, {"genre": "15"}, timeout)
        update_category_map(category_map, payload)
    except Exception as exc:  # Category names are helpful, not mandatory.
        print(f"[warn] category lookup failed: {exc}", file=sys.stderr)
    return category_map


def record_key(record: dict[str, Any]) -> str:
    value = first_value(record, ID_KEYS)
    if value not in (None, ""):
        return f"id:{value}"
    title = first_value(record, TITLE_KEYS)
    author = first_value(record, AUTHOR_KEYS)
    return f"title:{title}|author:{author}"


def build_params(args: argparse.Namespace, page_index: int) -> dict[str, Any]:
    params: dict[str, Any] = {
        "page_index": str(page_index),
        "page_size": str(args.page_size),
        "image_fmt": "90x120",
        "ip_source": "1",
        "ip_apply_type": "3",
    }
    if args.filter_gender:
        params["gender"] = args.filter_gender
    if args.word_num_gt:
        params["word_num_gt"] = args.word_num_gt
    if args.word_num_lt:
        params["word_num_lt"] = args.word_num_lt
    for item in args.extra_param:
        if "=" not in item:
            raise SystemExit(f"--extra-param must be key=value, got {item!r}")
        key, value = item.split("=", 1)
        params[key] = value
    return params


def fetch_records(session: requests.Session, args: argparse.Namespace) -> list[dict[str, Any]]:
    seen: set[str] = set()
    records: list[dict[str, Any]] = []
    page_index = 1
    while True:
        if args.max_pages and page_index > args.max_pages:
            break
        payload = request_json(session, LIST_URL, build_params(args, page_index), args.timeout)
        page_records = find_records(payload)
        print(f"[info] page {page_index}: {len(page_records)} records", file=sys.stderr)
        if not page_records:
            break
        for record in page_records:
            key = record_key(record)
            if key in seen:
                continue
            seen.add(key)
            records.append(record)
        if len(page_records) < args.page_size:
            break
        page_index += 1
        time.sleep(args.sleep)
    return records


def build_rows(records: list[dict[str, Any]], category_map: dict[str, str], include_raw: bool) -> tuple[list[str], list[OrderedDict[str, Any]]]:
    rows: list[OrderedDict[str, Any]] = []
    all_columns: OrderedDict[str, None] = OrderedDict((column, None) for column in FRIENDLY_COLUMNS)
    for record in records:
        row = friendly_row(record, category_map)
        flat = flatten(record)
        for key, value in flat.items():
            if key not in row:
                row[key] = value
                all_columns.setdefault(key, None)
        if include_raw:
            row["raw_json"] = json.dumps(record, ensure_ascii=False, separators=(",", ":"))
            all_columns.setdefault("raw_json", None)
        rows.append(row)
    return list(all_columns.keys()), rows


def write_csv(path: Path, columns: list[str], rows: list[OrderedDict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def write_xlsx(path: Path, columns: list[str], rows: list[OrderedDict[str, Any]]) -> None:
    try:
        from openpyxl import Workbook
    except ImportError as exc:
        raise SystemExit("XLSX export requires openpyxl. Install it or use --format csv.") from exc
    path.parent.mkdir(parents=True, exist_ok=True)
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "ip_export"
    sheet.append(columns)
    for row in rows:
        sheet.append([row.get(column, "") for column in columns])
    workbook.save(path)


def main() -> int:
    args = parse_args()
    cookies = resolve_cookies(args)
    session = requests.Session()
    session.cookies.update(cookies)
    session.headers.update(
        {
            "accept": "application/json, text/plain, */*",
            "accept-language": "zh-CN,zh;q=0.9",
            "referer": "https://creator.shortdramas.com/page/copyright/ip/list?tab=motion_comic",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36",
        }
    )

    category_map = {} if args.no_categories else fetch_categories(session, args.timeout)
    records = fetch_records(session, args)
    columns, rows = build_rows(records, category_map, args.include_raw)
    output = Path(args.output)

    if args.format in {"csv", "both"}:
        csv_path = output if output.suffix.lower() == ".csv" else output.with_suffix(".csv")
        write_csv(csv_path, columns, rows)
        print(f"[done] wrote {len(rows)} rows to {csv_path}")
    if args.format in {"xlsx", "both"}:
        xlsx_path = output if output.suffix.lower() == ".xlsx" else output.with_suffix(".xlsx")
        write_xlsx(xlsx_path, columns, rows)
        print(f"[done] wrote {len(rows)} rows to {xlsx_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
