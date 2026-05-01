#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable

import requests


BASE_URL = "https://creator.shortdramas.com"
DEFAULT_TIMEOUT = 30
DEFAULT_TTWID_PAYLOAD = {
    "aid": 791322,
    "service": "creator.shortdramas.com",
    "unionHost": "",
    "union": False,
    "needFid": False,
    "fid": "",
    "migrate_priority": 0,
}
DEFAULT_API_PARAMS = {
    "role_type": "3",
    "author_type": "1",
    "member_type": "3",
}
DEFAULT_FILTERS = {
    "playlet_source": 1,
    "genre": 15,
    "playlet_type": 1,
    "data_source": 2,
}
ID_KEYS = (
    "playlet_id",
    "id",
    "playletId",
)
TITLE_KEYS = (
    "playlet_name",
    "name",
    "title",
    "playlet_title",
    "drama_name",
    "series_name",
)
PUBLISH_KEYS = (
    "publish_time",
    "publish_date",
    "release_time",
    "release_date",
    "online_time",
    "online_date",
    "first_publish_time",
)
TOTAL_METRIC_KEY = "listen_dcnt_td"
TOTAL_METRIC_NAME = "累计播放量"
AVG_PLAY_EPISODES_METRIC_KEY = "avg_play_material_cnt_td"
PLAYLET_DURATION_METRIC_KEY = "playlet_duration"
FIRST_EPISODE_PROGRESS_KEY = "group_finish_rate_1th"
FINISH_10MIN_KEY = "group_finish_rate_td_10min"
FINISH_30MIN_KEY = "group_finish_rate_td_30min"
FINISH_60MIN_KEY = "group_finish_rate_td_60min"
EPISODE_PROGRESS_SERIES_KEY = "group_finish_percent_json"
EPISODE_CONTINUE_SERIES_KEY = "group_play_rate"
METRIC_NAME_KEYS = (
    "metric_key",
    "key",
    "metric",
    "name",
)
METRIC_VALUE_KEYS = (
    "value",
    "val",
    "count",
    "total",
    "metric_value",
    "sum",
    "server_vv",
)
DATE_KEYS = (
    "date",
    "dt",
    "day",
    "stat_date",
    "time",
    "index",
)
POINT_CONTAINER_KEYS = (
    "values",
    "value_list",
    "data_list",
    "series",
    "trend",
    "points",
    "data",
    "items",
    "list",
)


class ConfigError(RuntimeError):
    pass


@dataclass
class PlayletRecord:
    playlet_id: str
    title: str
    publish_date: str | None
    path: str
    raw: dict[str, Any]


def load_json(path: str) -> dict[str, Any]:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ConfigError(f"auth config not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ConfigError(f"auth config is not valid JSON: {path}") from exc


def dump_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def dump_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames: list[str] = []
    for row in rows:
        for key in row:
            if key not in fieldnames:
                fieldnames.append(key)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def to_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    if is_number(value):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


def to_int(value: Any) -> int | None:
    as_float = to_float(value)
    if as_float is None:
        return None
    return int(round(as_float))


def normalize_title(value: str) -> str:
    return re.sub(r"[\W_]+", "", value.lower())


def coerce_yyyymmdd(value: Any) -> str | None:
    if value in (None, ""):
        return None
    if isinstance(value, str):
        stripped = value.strip()
        if re.fullmatch(r"\d{8}", stripped):
            return stripped
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", stripped):
            return stripped.replace("-", "")
        if re.fullmatch(r"\d{4}/\d{2}/\d{2}", stripped):
            return stripped.replace("/", "")
        if stripped.isdigit():
            value = int(stripped)
        else:
            return None
    if isinstance(value, (int, float)):
        number = int(value)
        if number > 10**12:
            dt = datetime.utcfromtimestamp(number / 1000)
            return dt.strftime("%Y%m%d")
        if number > 10**9:
            dt = datetime.utcfromtimestamp(number)
            return dt.strftime("%Y%m%d")
    return None


def coerce_iso_date(value: Any) -> str | None:
    normalized = coerce_yyyymmdd(value)
    if normalized is None:
        return None
    return f"{normalized[:4]}-{normalized[4:6]}-{normalized[6:8]}"


def first_non_empty(mapping: dict[str, Any], keys: Iterable[str]) -> Any:
    for key in keys:
        value = mapping.get(key)
        if value not in (None, ""):
            return value
    return None


def walk_nodes(node: Any, path: str = "$") -> Iterable[tuple[str, Any]]:
    yield path, node
    if isinstance(node, dict):
        for key, value in node.items():
            yield from walk_nodes(value, f"{path}.{key}")
    elif isinstance(node, list):
        for index, value in enumerate(node):
            yield from walk_nodes(value, f"{path}[{index}]")


def extract_playlets(payload: Any) -> list[PlayletRecord]:
    records: dict[str, PlayletRecord] = {}
    for path, node in walk_nodes(payload):
        if not isinstance(node, dict):
            continue
        playlet_id = first_non_empty(node, ID_KEYS)
        title = first_non_empty(node, TITLE_KEYS)
        if playlet_id in (None, "") or title in (None, ""):
            continue
        playlet_id = str(playlet_id)
        record = PlayletRecord(
            playlet_id=playlet_id,
            title=str(title),
            publish_date=coerce_yyyymmdd(first_non_empty(node, PUBLISH_KEYS)),
            path=path,
            raw=node,
        )
        records.setdefault(playlet_id, record)
    return list(records.values())


def resolve_playlet(records: list[PlayletRecord], title: str | None, playlet_id: str | None) -> PlayletRecord:
    if playlet_id:
        for record in records:
            if record.playlet_id == str(playlet_id):
                return record
        raise ConfigError(f"playlet_id not found in selected playlets: {playlet_id}")

    if not title:
        raise ConfigError("either --title or --playlet-id is required")

    normalized_target = normalize_title(title)
    exact_matches = [record for record in records if normalize_title(record.title) == normalized_target]
    if len(exact_matches) == 1:
        return exact_matches[0]
    if len(exact_matches) > 1:
        raise ConfigError(
            "multiple exact title matches found: "
            + ", ".join(f"{item.title} ({item.playlet_id})" for item in exact_matches)
        )

    fuzzy_matches = [record for record in records if normalized_target in normalize_title(record.title)]
    if len(fuzzy_matches) == 1:
        return fuzzy_matches[0]
    if len(fuzzy_matches) > 1:
        raise ConfigError(
            "multiple fuzzy title matches found: "
            + ", ".join(f"{item.title} ({item.playlet_id})" for item in fuzzy_matches)
        )

    raise ConfigError(f"title not found in selected playlets: {title}")


def find_first_subtree_for_playlet(payload: Any, playlet_id: str) -> Any:
    for _, node in walk_nodes(payload):
        if isinstance(node, dict):
            node_id = first_non_empty(node, ID_KEYS)
            if node_id is not None and str(node_id) == str(playlet_id):
                return node
    return payload


def find_metric_value_candidates(payload: Any, metric_key: str) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for path, node in walk_nodes(payload):
        if not isinstance(node, dict):
            continue
        direct_value = node.get(metric_key)
        if is_number(direct_value):
            candidates.append({"path": f"{path}.{metric_key}", "value": float(direct_value)})
        metric_name = first_non_empty(node, METRIC_NAME_KEYS)
        if metric_name == metric_key:
            for value_key in METRIC_VALUE_KEYS:
                value = node.get(value_key)
                if is_number(value):
                    candidates.append({"path": f"{path}.{value_key}", "value": float(value)})
    deduped: list[dict[str, Any]] = []
    seen = set()
    for item in candidates:
        signature = (item["path"], item["value"])
        if signature not in seen:
            seen.add(signature)
            deduped.append(item)
    return deduped


def parse_points_from_container(container: Any, metric_key: str) -> list[dict[str, Any]]:
    if isinstance(container, list):
        direct_points: list[dict[str, Any]] = []
        for item in container:
            item_value = to_float(item)
            if item_value is not None:
                direct_points.append({"date": None, "value": item_value})
                continue
            if isinstance(item, dict):
                value = first_non_empty(item, METRIC_VALUE_KEYS)
                if to_float(value) is None:
                    value = item.get(metric_key)
                numeric_value = to_float(value)
                if numeric_value is not None:
                    direct_points.append(
                        {
                            "date": first_non_empty(item, DATE_KEYS),
                            "value": numeric_value,
                        }
                    )
        if direct_points:
            return direct_points

        best_nested: list[dict[str, Any]] = []
        for item in container:
            nested = parse_points_from_container(item, metric_key)
            if len(nested) > len(best_nested):
                best_nested = nested
        return best_nested

    if isinstance(container, dict):
        if container and all(re.fullmatch(r"\d{8}", str(key)) for key in container):
            if all(to_float(value) is not None for value in container.values()):
                return [{"date": str(key), "value": to_float(value)} for key, value in container.items()]

        direct_value = first_non_empty(container, METRIC_VALUE_KEYS)
        if to_float(direct_value) is None:
            direct_value = container.get(metric_key)
        numeric_value = to_float(direct_value)
        if numeric_value is not None:
            return [{"date": first_non_empty(container, DATE_KEYS), "value": numeric_value}]

        for key in POINT_CONTAINER_KEYS:
            if key in container:
                nested = parse_points_from_container(container[key], metric_key)
                if nested:
                    return nested

    return []


def extract_metric_points(payload: Any, metric_key: str) -> list[dict[str, Any]]:
    best_points: list[dict[str, Any]] = []
    for _, node in walk_nodes(payload):
        if not isinstance(node, dict):
            continue
        if metric_key in node:
            points = parse_points_from_container(node[metric_key], metric_key)
            if len(points) > len(best_points):
                best_points = points
        metric_name = first_non_empty(node, METRIC_NAME_KEYS)
        if metric_name == metric_key:
            for key in POINT_CONTAINER_KEYS:
                if key in node:
                    points = parse_points_from_container(node[key], metric_key)
                    if len(points) > len(best_points):
                        best_points = points
        meta = node.get("meta")
        if isinstance(meta, dict) and meta.get("key") == metric_key:
            for key in POINT_CONTAINER_KEYS:
                if key in node:
                    points = parse_points_from_container(node[key], metric_key)
                    if len(points) > len(best_points):
                        best_points = points
    return best_points


class CopyrightMetricsClient:
    def __init__(self, auth: dict[str, Any]) -> None:
        self.timeout = int(auth.get("timeout", DEFAULT_TIMEOUT))
        self.api_params = {**DEFAULT_API_PARAMS, **auth.get("api_params", {})}
        self.filters = {**DEFAULT_FILTERS, **auth.get("filters", {})}
        self.ttwid_payload = auth.get("ttwid_payload", DEFAULT_TTWID_PAYLOAD)
        self.skip_ttwid = bool(auth.get("skip_ttwid", False))

        self.session = requests.Session()
        self.session.headers.update(self._clean_headers(auth.get("headers", {})))
        self.session.cookies.update(auth.get("cookies", {}))

    @staticmethod
    def _clean_headers(headers: dict[str, Any]) -> dict[str, str]:
        cleaned: dict[str, str] = {}
        for key, value in headers.items():
            if key.lower() == "cookie":
                continue
            cleaned[str(key)] = str(value)
        return cleaned

    def _post(self, path: str, *, params: dict[str, Any] | None = None, payload: dict[str, Any] | None = None) -> Any:
        url = path if path.startswith("http") else f"{BASE_URL}{path}"
        response = self.session.post(url, params=params, json=payload, timeout=self.timeout)
        response.raise_for_status()
        return response.json()

    def warmup_ttwid(self) -> Any:
        if self.skip_ttwid:
            return {"skipped": True}
        return self._post("/ttwid/check/", payload=self.ttwid_payload)

    def list_selected_playlets(self) -> Any:
        payload = {
            "publish_time": {},
            "playlet_id_list": [],
            "auth_uid": "",
            "playlet_source": self.filters["playlet_source"],
            "genre": self.filters["genre"],
            "playlet_type": self.filters["playlet_type"],
        }
        return self._post(
            "/api/playlet/data_analysis/selected_playlet/list/v1",
            params=self.api_params,
            payload=payload,
        )

    def fetch_overview(self, playlet_id: str, start_date: str, end_date: str) -> Any:
        payload = {
            "data_source": self.filters["data_source"],
            "time_range": {
                "start_time": start_date,
                "end_time": end_date,
                "unit": "day",
            },
            "playlet_ids": [playlet_id],
            "playlet_source": self.filters["playlet_source"],
            "genre": self.filters["genre"],
        }
        return self._post(
            "/api/playlet/metric/overview/v1",
            params=self.api_params,
            payload=payload,
        )

    def fetch_trend(self, playlet_id: str, start_date: str, end_date: str, metric_key: str) -> Any:
        payload = {
            "data_source": self.filters["data_source"],
            "time_range": {
                "start_time": start_date,
                "end_time": end_date,
                "unit": "day",
            },
            "playlet_ids": [playlet_id],
            "need_last_period_trending": False,
            "metric_keys": [metric_key],
            "playlet_source": self.filters["playlet_source"],
            "genre": self.filters["genre"],
        }
        return self._post(
            "/api/playlet/metric/trend/v1",
            params=self.api_params,
            payload=payload,
        )

    def fetch_rank_list(
        self,
        playlet_ids: list[str],
        start_date: str,
        end_date: str,
        *,
        rank_key: str = "publish_time",
        rank_type: str = "desc",
        offset: int = 0,
        limit: int | None = None,
    ) -> Any:
        payload = {
            "playlet_ids": playlet_ids,
            "time_range": {
                "start_time": start_date,
                "end_time": end_date,
                "unit": "day",
            },
            "rank": {
                "key": rank_key,
                "type": rank_type,
            },
            "date_source": self.filters["data_source"],
            "offset": offset,
            "limit": limit if limit is not None else max(len(playlet_ids), 20),
            "playlet_source": self.filters["playlet_source"],
            "genre": self.filters["genre"],
        }
        return self._post(
            "/api/playlet/rank/list/v1",
            params=self.api_params,
            payload=payload,
        )


def chunked(values: list[str], size: int) -> Iterable[list[str]]:
    for index in range(0, len(values), size):
        yield values[index : index + size]


def extract_total_play_rows(
    payload: Any,
    *,
    metric_key: str = TOTAL_METRIC_KEY,
    metric_name: str = TOTAL_METRIC_NAME,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    playlet_ranks = payload.get("data", {}).get("playlet_ranks", [])
    for item in playlet_ranks:
        total_play_count = None
        matched_metric_key = None
        matched_metric_name = None
        for metric in item.get("metrics", []):
            meta = metric.get("meta", {})
            data = metric.get("data", {})
            if meta.get("key") == metric_key or meta.get("name") == metric_name:
                total_play_count = data.get("value")
                matched_metric_key = meta.get("key")
                matched_metric_name = meta.get("name")
                break
        if isinstance(total_play_count, str) and total_play_count.isdigit():
            total_play_count = int(total_play_count)
        elif isinstance(total_play_count, str):
            try:
                total_play_count = int(float(total_play_count))
            except ValueError:
                pass
        publish_time = item.get("publish_time")
        rows.append(
            {
                "playlet_id": str(item.get("playlet_id", "")),
                "title": item.get("playlet_name"),
                "publish_time": publish_time,
                "publish_date": coerce_iso_date(publish_time),
                "total_play_count": total_play_count,
                "metric_key": matched_metric_key,
                "metric_name": matched_metric_name,
                "seq_cnt": item.get("seq_cnt"),
            }
        )
    return rows


def metric_lookup(item: dict[str, Any]) -> dict[str, dict[str, Any]]:
    lookup: dict[str, dict[str, Any]] = {}
    for metric in item.get("metrics", []):
        key = metric.get("meta", {}).get("key")
        if key:
            lookup[str(key)] = metric
    return lookup


def series_lookup(item: dict[str, Any]) -> dict[str, dict[str, Any]]:
    lookup: dict[str, dict[str, Any]] = {}
    for metric in item.get("metrics_series", []):
        key = metric.get("meta", {}).get("key")
        if key:
            lookup[str(key)] = metric
    return lookup


def get_metric_value(item: dict[str, Any], key: str) -> float | None:
    metric = metric_lookup(item).get(key)
    if not metric:
        return None
    return to_float(metric.get("data", {}).get("value"))


def get_metric_name(item: dict[str, Any], key: str) -> str | None:
    metric = metric_lookup(item).get(key)
    if not metric:
        return None
    return metric.get("meta", {}).get("name")


def get_series_values(item: dict[str, Any], key: str) -> list[float]:
    series = series_lookup(item).get(key)
    if not series:
        return []
    values: list[float] = []
    for point in series.get("data_list", []):
        value = to_float(point.get("value"))
        if value is not None:
            values.append(value)
    return values


def average(values: list[float]) -> float | None:
    if not values:
        return None
    return sum(values) / len(values)


def estimate_effective_minutes(
    *,
    total_play_count: float | None,
    total_duration_min: float | None,
    seq_cnt: int | None,
    avg_play_episodes: float | None,
    avg_episode_progress_rate: float | None,
) -> float | None:
    if None in (total_play_count, total_duration_min, seq_cnt, avg_play_episodes, avg_episode_progress_rate):
        return None
    if not seq_cnt:
        return None
    episode_duration = total_duration_min / seq_cnt
    return total_play_count * avg_play_episodes * episode_duration * avg_episode_progress_rate


def estimate_lower_bound_minutes_from_time_buckets(
    *,
    total_play_count: float | None,
    total_duration_min: float | None,
    finish_10min_rate: float | None,
    finish_30min_rate: float | None,
    finish_60min_rate: float | None,
) -> float | None:
    if total_play_count is None or total_duration_min is None:
        return None
    rate10 = max((finish_10min_rate or 0.0) / 100.0, 0.0)
    rate30 = max((finish_30min_rate or 0.0) / 100.0, 0.0)
    rate60 = max((finish_60min_rate or 0.0) / 100.0, 0.0)
    first_segment = min(total_duration_min, 10.0) * rate10
    second_segment = max(min(total_duration_min, 30.0) - 10.0, 0.0) * rate30
    third_segment = max(min(total_duration_min, 60.0) - 30.0, 0.0) * rate60
    return total_play_count * (first_segment + second_segment + third_segment)


def estimate_duration_adjusted_minutes(
    *,
    total_play_count: float | None,
    total_duration_min: float | None,
    estimated_effective_minutes: float | None,
    lower_bound_effective_minutes: float | None,
) -> float | None:
    if total_play_count is None or total_duration_min is None:
        return None
    candidates = [value for value in (estimated_effective_minutes, lower_bound_effective_minutes) if value is not None]
    if not candidates:
        return None
    max_possible_minutes = total_play_count * total_duration_min
    return min(max(candidates), max_possible_minutes)


def derive_effective_minutes_for_play_count(row: dict[str, Any], play_count: float | None) -> dict[str, float | None]:
    total_duration_min = to_float(row.get("playlet_duration_min"))
    seq_cnt = to_int(row.get("seq_cnt"))
    avg_play_episodes = to_float(row.get("avg_play_episodes_per_viewer"))
    avg_episode_progress_pct = to_float(row.get("avg_episode_progress_pct"))
    avg_episode_progress_rate = None if avg_episode_progress_pct is None else avg_episode_progress_pct / 100.0
    estimated_minutes = estimate_effective_minutes(
        total_play_count=play_count,
        total_duration_min=total_duration_min,
        seq_cnt=seq_cnt,
        avg_play_episodes=avg_play_episodes,
        avg_episode_progress_rate=avg_episode_progress_rate,
    )
    lower_bound_minutes = estimate_lower_bound_minutes_from_time_buckets(
        total_play_count=play_count,
        total_duration_min=total_duration_min,
        finish_10min_rate=to_float(row.get("finish_10min_rate_pct")),
        finish_30min_rate=to_float(row.get("finish_30min_rate_pct")),
        finish_60min_rate=to_float(row.get("finish_60min_rate_pct")),
    )
    duration_adjusted_minutes = estimate_duration_adjusted_minutes(
        total_play_count=play_count,
        total_duration_min=total_duration_min,
        estimated_effective_minutes=estimated_minutes,
        lower_bound_effective_minutes=lower_bound_minutes,
    )
    return {
        "estimated_effective_minutes": estimated_minutes,
        "estimated_effective_hours": None if estimated_minutes is None else estimated_minutes / 60.0,
        "lower_bound_effective_minutes": lower_bound_minutes,
        "lower_bound_effective_hours": None if lower_bound_minutes is None else lower_bound_minutes / 60.0,
        "duration_adjusted_effective_minutes": duration_adjusted_minutes,
        "duration_adjusted_effective_hours": None
        if duration_adjusted_minutes is None
        else duration_adjusted_minutes / 60.0,
    }


def extract_completion_rows(payload: Any) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    playlet_ranks = payload.get("data", {}).get("playlet_ranks", [])
    for item in playlet_ranks:
        total_play_count = to_int(get_metric_value(item, TOTAL_METRIC_KEY))
        total_duration_min = to_float(get_metric_value(item, PLAYLET_DURATION_METRIC_KEY))
        avg_play_episodes = to_float(get_metric_value(item, AVG_PLAY_EPISODES_METRIC_KEY))
        first_episode_progress = to_float(get_metric_value(item, FIRST_EPISODE_PROGRESS_KEY))
        finish_10min_rate = to_float(get_metric_value(item, FINISH_10MIN_KEY))
        finish_30min_rate = to_float(get_metric_value(item, FINISH_30MIN_KEY))
        finish_60min_rate = to_float(get_metric_value(item, FINISH_60MIN_KEY))
        seq_cnt = to_int(item.get("seq_cnt"))
        episode_progress_values = get_series_values(item, EPISODE_PROGRESS_SERIES_KEY)
        episode_continue_values = get_series_values(item, EPISODE_CONTINUE_SERIES_KEY)
        avg_episode_progress_pct = average(episode_progress_values)
        avg_episode_continue_pct = average(episode_continue_values)
        avg_episode_progress_rate = None if avg_episode_progress_pct is None else avg_episode_progress_pct / 100.0
        estimated_effective_play_minutes = estimate_effective_minutes(
            total_play_count=to_float(total_play_count),
            total_duration_min=total_duration_min,
            seq_cnt=seq_cnt,
            avg_play_episodes=avg_play_episodes,
            avg_episode_progress_rate=avg_episode_progress_rate,
        )
        lower_bound_effective_minutes = estimate_lower_bound_minutes_from_time_buckets(
            total_play_count=to_float(total_play_count),
            total_duration_min=total_duration_min,
            finish_10min_rate=finish_10min_rate,
            finish_30min_rate=finish_30min_rate,
            finish_60min_rate=finish_60min_rate,
        )
        duration_adjusted_effective_minutes = estimate_duration_adjusted_minutes(
            total_play_count=to_float(total_play_count),
            total_duration_min=total_duration_min,
            estimated_effective_minutes=estimated_effective_play_minutes,
            lower_bound_effective_minutes=lower_bound_effective_minutes,
        )
        episode_duration_min = None
        if total_duration_min is not None and seq_cnt:
            episode_duration_min = total_duration_min / seq_cnt

        rows.append(
            {
                "playlet_id": str(item.get("playlet_id", "")),
                "title": item.get("playlet_name"),
                "publish_date": coerce_iso_date(item.get("publish_time")),
                "publish_time": item.get("publish_time"),
                "seq_cnt": seq_cnt,
                "playlet_duration_min": total_duration_min,
                "playlet_total_duration_min": total_duration_min,
                "avg_episode_duration_min": episode_duration_min,
                "total_play_count": total_play_count,
                "avg_play_episodes_per_viewer": avg_play_episodes,
                "first_episode_finish_progress_pct": first_episode_progress,
                "finish_10min_rate_pct": finish_10min_rate,
                "finish_30min_rate_pct": finish_30min_rate,
                "finish_60min_rate_pct": finish_60min_rate,
                "avg_episode_progress_pct": avg_episode_progress_pct,
                "avg_episode_continue_pct": avg_episode_continue_pct,
                "estimated_effective_play_minutes": estimated_effective_play_minutes,
                "estimated_effective_play_hours": None
                if estimated_effective_play_minutes is None
                else estimated_effective_play_minutes / 60.0,
                "lower_bound_effective_minutes": lower_bound_effective_minutes,
                "lower_bound_effective_hours": None
                if lower_bound_effective_minutes is None
                else lower_bound_effective_minutes / 60.0,
                "duration_adjusted_effective_minutes": duration_adjusted_effective_minutes,
                "duration_adjusted_effective_hours": None
                if duration_adjusted_effective_minutes is None
                else duration_adjusted_effective_minutes / 60.0,
                "estimate_formula": "total_play_count * avg_play_episodes_per_viewer * avg_episode_duration_min * avg_episode_progress_pct",
                "lower_bound_formula": "total_play_count * (10min_rate*10 + 30min_rate*extra_20 + 60min_rate*extra_30)",
                "duration_adjusted_formula": "min(total_play_count * playlet_total_duration_min, max(estimated_effective_play_minutes, lower_bound_effective_minutes))",
            }
        )
    return rows


def resolve_report_row(
    rows: list[dict[str, Any]],
    *,
    title: str | None,
    playlet_id: str | None,
) -> dict[str, Any]:
    if playlet_id:
        for row in rows:
            if row.get("playlet_id") == str(playlet_id):
                return row
        raise ConfigError(f"benchmark playlet_id not found in report rows: {playlet_id}")

    if not title:
        raise ConfigError("benchmark requires either --benchmark-title or --benchmark-playlet-id")

    normalized_target = normalize_title(title)
    exact_matches = [row for row in rows if normalize_title(str(row.get("title", ""))) == normalized_target]
    if len(exact_matches) == 1:
        return exact_matches[0]
    if len(exact_matches) > 1:
        raise ConfigError(
            "multiple exact benchmark title matches found: "
            + ", ".join(f"{row.get('title')} ({row.get('playlet_id')})" for row in exact_matches)
        )

    fuzzy_matches = [row for row in rows if normalized_target in normalize_title(str(row.get("title", "")))]
    if len(fuzzy_matches) == 1:
        return fuzzy_matches[0]
    if len(fuzzy_matches) > 1:
        raise ConfigError(
            "multiple fuzzy benchmark title matches found: "
            + ", ".join(f"{row.get('title')} ({row.get('playlet_id')})" for row in fuzzy_matches)
        )

    raise ConfigError(f"benchmark title not found in report rows: {title}")


def extract_metric_sum(payload: Any, metric_key: str) -> int | None:
    points = extract_metric_points(payload, metric_key)
    if not points:
        return None
    return int(round(sum(point["value"] for point in points)))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Fetch short-drama metrics from creator.shortdramas.com.")
    parser.add_argument("--auth", required=True, help="Path to auth config JSON.")
    parser.add_argument("--dump-response-dir", help="Optional directory for raw API responses.")
    parser.add_argument("--output", help="Optional output path. Supports .json and .csv.")

    subparsers = parser.add_subparsers(dest="command", required=True)

    list_parser = subparsers.add_parser("list", help="List selected playlets visible to the current auth.")
    list_parser.add_argument("--title", help="Optional title filter.")

    total_parser = subparsers.add_parser("total", help="Resolve one playlet and compute total plays.")
    total_parser.add_argument("--title", help="Playlet title to resolve.")
    total_parser.add_argument("--playlet-id", help="Playlet ID to query directly.")
    total_parser.add_argument("--metric-key", default="server_vv", help="Metric key to read from trend API.")
    total_parser.add_argument("--start-date", help="Override start date in YYYYMMDD.")
    total_parser.add_argument("--end-date", help="Override end date in YYYYMMDD. Defaults to today.")
    total_parser.add_argument("--skip-overview", action="store_true", help="Skip overview API and use trend only.")

    all_totals_parser = subparsers.add_parser(
        "all-totals",
        help="Fetch cumulative play totals for all visible playlets in one run.",
    )
    all_totals_parser.add_argument(
        "--start-date",
        default="20200101",
        help="Wide query start date in YYYYMMDD for rank/list. Defaults to 20200101.",
    )
    all_totals_parser.add_argument("--end-date", help="Query end date in YYYYMMDD. Defaults to today.")
    all_totals_parser.add_argument(
        "--batch-size",
        type=int,
        default=20,
        help="How many playlet IDs to request per rank/list batch. Defaults to 20.",
    )
    all_totals_parser.add_argument(
        "--title",
        help="Optional title filter before requesting totals.",
    )

    all_completion_parser = subparsers.add_parser(
        "all-completion",
        help="Fetch completion metrics for all visible playlets and estimate effective watched time.",
    )
    all_completion_parser.add_argument(
        "--start-date",
        default="20200101",
        help="Wide query start date in YYYYMMDD for rank/list. Defaults to 20200101.",
    )
    all_completion_parser.add_argument("--end-date", help="Query end date in YYYYMMDD. Defaults to today.")
    all_completion_parser.add_argument(
        "--batch-size",
        type=int,
        default=20,
        help="How many playlet IDs to request per rank/list batch. Defaults to 20.",
    )
    all_completion_parser.add_argument(
        "--title",
        help="Optional title filter before requesting completion metrics.",
    )

    revenue_parser = subparsers.add_parser(
        "revenue-report",
        help="Pull totals and completion metrics for all visible playlets, then estimate revenue from a benchmark.",
    )
    revenue_parser.add_argument(
        "--start-date",
        default="20200101",
        help="Wide query start date in YYYYMMDD for rank/list. Defaults to 20200101.",
    )
    revenue_parser.add_argument("--end-date", help="Query end date in YYYYMMDD. Defaults to today.")
    revenue_parser.add_argument(
        "--batch-size",
        type=int,
        default=20,
        help="How many playlet IDs to request per rank/list batch. Defaults to 20.",
    )
    revenue_parser.add_argument(
        "--title",
        help="Optional title filter before requesting the report rows.",
    )
    revenue_parser.add_argument(
        "--benchmark-title",
        help="Benchmark playlet title used to scale estimated revenue.",
    )
    revenue_parser.add_argument(
        "--benchmark-playlet-id",
        help="Benchmark playlet ID used to scale estimated revenue.",
    )
    revenue_parser.add_argument(
        "--benchmark-revenue",
        type=float,
        required=True,
        help="Known revenue for the benchmark playlet.",
    )
    revenue_parser.add_argument(
        "--revenue-basis",
        choices=(
            "settlement_duration_adjusted_effective_hours",
            "settlement_lower_bound_effective_hours",
            "settlement_play_count",
            "duration_adjusted_effective_hours",
            "lower_bound_effective_hours",
            "estimated_effective_play_hours",
            "total_play_count",
        ),
        help="Metric used to scale benchmark revenue. Defaults to settlement_duration_adjusted_effective_hours when a settlement window is supplied; otherwise duration_adjusted_effective_hours.",
    )
    revenue_parser.add_argument(
        "--settlement-start-date",
        help="Optional revenue-settlement play window start date in YYYYMMDD. Uses trend server_vv sums.",
    )
    revenue_parser.add_argument(
        "--settlement-end-date",
        help="Optional revenue-settlement play window end date in YYYYMMDD. Uses trend server_vv sums.",
    )
    revenue_parser.add_argument(
        "--settlement-metric-key",
        default="server_vv",
        help="Trend metric key used for settlement play counts. Defaults to server_vv.",
    )

    return parser


def handle_list(args: argparse.Namespace, client: CopyrightMetricsClient, dump_dir: Path | None) -> dict[str, Any]:
    warmup = client.warmup_ttwid()
    payload = client.list_selected_playlets()
    if dump_dir:
        dump_json(dump_dir / "ttwid-check.json", warmup)
        dump_json(dump_dir / "selected-playlets.json", payload)

    playlets = extract_playlets(payload)
    if args.title:
        normalized = normalize_title(args.title)
        playlets = [item for item in playlets if normalized in normalize_title(item.title)]

    return {
        "count": len(playlets),
        "playlets": [
            {
                "playlet_id": item.playlet_id,
                "title": item.title,
                "publish_date": item.publish_date,
            }
            for item in playlets
        ],
    }


def handle_total(args: argparse.Namespace, client: CopyrightMetricsClient, dump_dir: Path | None) -> dict[str, Any]:
    warmup = client.warmup_ttwid()
    selected_payload = client.list_selected_playlets()
    playlets = extract_playlets(selected_payload)
    target = resolve_playlet(playlets, title=args.title, playlet_id=args.playlet_id)

    start_date = args.start_date or target.publish_date
    if not start_date:
        raise ConfigError("publish date not found in selected playlets; rerun with --start-date YYYYMMDD")
    if not coerce_yyyymmdd(start_date):
        raise ConfigError(f"invalid start date: {start_date}")
    start_date = coerce_yyyymmdd(start_date)

    end_date = args.end_date or date.today().strftime("%Y%m%d")
    if not coerce_yyyymmdd(end_date):
        raise ConfigError(f"invalid end date: {end_date}")
    end_date = coerce_yyyymmdd(end_date)

    overview_payload = None
    if not args.skip_overview:
        overview_payload = client.fetch_overview(target.playlet_id, start_date, end_date)
    trend_payload = client.fetch_trend(target.playlet_id, start_date, end_date, args.metric_key)

    trend_subtree = find_first_subtree_for_playlet(trend_payload, target.playlet_id)
    overview_subtree = (
        find_first_subtree_for_playlet(overview_payload, target.playlet_id) if overview_payload is not None else None
    )

    trend_points = extract_metric_points(trend_subtree, args.metric_key)
    trend_sum = int(round(sum(point["value"] for point in trend_points))) if trend_points else None
    overview_candidates = (
        find_metric_value_candidates(overview_subtree, args.metric_key) if overview_subtree is not None else []
    )

    if dump_dir:
        dump_json(dump_dir / "ttwid-check.json", warmup)
        dump_json(dump_dir / "selected-playlets.json", selected_payload)
        if overview_payload is not None:
            dump_json(dump_dir / "metric-overview.json", overview_payload)
        dump_json(dump_dir / "metric-trend.json", trend_payload)

    total_play_count = trend_sum
    total_source = "trend_sum"
    if total_play_count is None and overview_candidates:
        total_play_count = int(round(overview_candidates[0]["value"]))
        total_source = "overview_candidate"

    return {
        "title": target.title,
        "playlet_id": target.playlet_id,
        "publish_date": target.publish_date,
        "range": {
            "start_date": start_date,
            "end_date": end_date,
            "used_publish_date_as_start": args.start_date is None,
        },
        "metric_key": args.metric_key,
        "total_play_count": total_play_count,
        "total_source": total_source,
        "trend_point_count": len(trend_points),
        "trend_points_preview": trend_points[:10],
        "overview_candidates": overview_candidates[:10],
        "warnings": [
            warning
            for warning in [
                None if total_play_count is not None else "no total metric could be derived",
                None if trend_points else "trend payload did not expose a recognizable metric series",
            ]
            if warning
        ],
    }


def handle_all_totals(args: argparse.Namespace, client: CopyrightMetricsClient, dump_dir: Path | None) -> dict[str, Any]:
    warmup = client.warmup_ttwid()
    selected_payload = client.list_selected_playlets()
    playlets = extract_playlets(selected_payload)
    if args.title:
        normalized = normalize_title(args.title)
        playlets = [item for item in playlets if normalized in normalize_title(item.title)]

    if not playlets:
        raise ConfigError("no visible playlets matched the requested filter")

    if not coerce_yyyymmdd(args.start_date):
        raise ConfigError(f"invalid start date: {args.start_date}")
    start_date = coerce_yyyymmdd(args.start_date)

    end_date = args.end_date or date.today().strftime("%Y%m%d")
    if not coerce_yyyymmdd(end_date):
        raise ConfigError(f"invalid end date: {end_date}")
    end_date = coerce_yyyymmdd(end_date)

    batch_size = max(1, int(args.batch_size))
    raw_batches: list[Any] = []
    rows: list[dict[str, Any]] = []
    requested_ids = [item.playlet_id for item in playlets]
    for batch_index, playlet_id_batch in enumerate(chunked(requested_ids, batch_size), start=1):
        payload = client.fetch_rank_list(playlet_id_batch, start_date, end_date, limit=max(len(playlet_id_batch), 20))
        raw_batches.append(payload)
        batch_rows = extract_total_play_rows(payload)
        for row in batch_rows:
            row["batch_index"] = batch_index
        rows.extend(batch_rows)

    rows_by_id = {row["playlet_id"]: row for row in rows}
    merged_rows: list[dict[str, Any]] = []
    for playlet in playlets:
        row = rows_by_id.get(playlet.playlet_id, {})
        merged_rows.append(
            {
                "playlet_id": playlet.playlet_id,
                "title": playlet.title,
                "publish_date": row.get("publish_date"),
                "publish_time": row.get("publish_time"),
                "total_play_count": row.get("total_play_count"),
                "metric_key": row.get("metric_key"),
                "metric_name": row.get("metric_name"),
                "seq_cnt": row.get("seq_cnt"),
                "batch_index": row.get("batch_index"),
            }
        )

    if dump_dir:
        dump_json(dump_dir / "ttwid-check.json", warmup)
        dump_json(dump_dir / "selected-playlets.json", selected_payload)
        dump_json(dump_dir / "rank-list-batches.json", raw_batches)

    return {
        "count": len(merged_rows),
        "range": {
            "start_date": start_date,
            "end_date": end_date,
        },
        "metric_key": TOTAL_METRIC_KEY,
        "metric_name": TOTAL_METRIC_NAME,
        "rows": merged_rows,
        "warnings": [
            warning
            for warning in [
                None
                if all(row.get("total_play_count") is not None for row in merged_rows)
                else "some playlets did not return a cumulative play count from rank/list",
            ]
            if warning
        ],
    }


def handle_all_completion(args: argparse.Namespace, client: CopyrightMetricsClient, dump_dir: Path | None) -> dict[str, Any]:
    warmup = client.warmup_ttwid()
    selected_payload = client.list_selected_playlets()
    playlets = extract_playlets(selected_payload)
    if args.title:
        normalized = normalize_title(args.title)
        playlets = [item for item in playlets if normalized in normalize_title(item.title)]

    if not playlets:
        raise ConfigError("no visible playlets matched the requested filter")

    if not coerce_yyyymmdd(args.start_date):
        raise ConfigError(f"invalid start date: {args.start_date}")
    start_date = coerce_yyyymmdd(args.start_date)

    end_date = args.end_date or date.today().strftime("%Y%m%d")
    if not coerce_yyyymmdd(end_date):
        raise ConfigError(f"invalid end date: {end_date}")
    end_date = coerce_yyyymmdd(end_date)

    batch_size = max(1, int(args.batch_size))
    raw_batches: list[Any] = []
    rows: list[dict[str, Any]] = []
    requested_ids = [item.playlet_id for item in playlets]
    for batch_index, playlet_id_batch in enumerate(chunked(requested_ids, batch_size), start=1):
        payload = client.fetch_rank_list(playlet_id_batch, start_date, end_date, limit=max(len(playlet_id_batch), 20))
        raw_batches.append(payload)
        batch_rows = extract_completion_rows(payload)
        for row in batch_rows:
            row["batch_index"] = batch_index
        rows.extend(batch_rows)

    rows_by_id = {row["playlet_id"]: row for row in rows}
    merged_rows: list[dict[str, Any]] = []
    for playlet in playlets:
        row = rows_by_id.get(playlet.playlet_id, {})
        merged_rows.append(
            {
                "playlet_id": playlet.playlet_id,
                "title": playlet.title,
                "publish_date": row.get("publish_date"),
                "publish_time": row.get("publish_time"),
                "seq_cnt": row.get("seq_cnt"),
                "playlet_duration_min": row.get("playlet_duration_min"),
                "avg_episode_duration_min": row.get("avg_episode_duration_min"),
                "total_play_count": row.get("total_play_count"),
                "avg_play_episodes_per_viewer": row.get("avg_play_episodes_per_viewer"),
                "first_episode_finish_progress_pct": row.get("first_episode_finish_progress_pct"),
                "finish_10min_rate_pct": row.get("finish_10min_rate_pct"),
                "finish_30min_rate_pct": row.get("finish_30min_rate_pct"),
                "finish_60min_rate_pct": row.get("finish_60min_rate_pct"),
                "avg_episode_progress_pct": row.get("avg_episode_progress_pct"),
                "avg_episode_continue_pct": row.get("avg_episode_continue_pct"),
                "estimated_effective_play_minutes": row.get("estimated_effective_play_minutes"),
                "estimated_effective_play_hours": row.get("estimated_effective_play_hours"),
                "lower_bound_effective_minutes": row.get("lower_bound_effective_minutes"),
                "lower_bound_effective_hours": row.get("lower_bound_effective_hours"),
                "duration_adjusted_effective_minutes": row.get("duration_adjusted_effective_minutes"),
                "duration_adjusted_effective_hours": row.get("duration_adjusted_effective_hours"),
                "estimate_formula": row.get("estimate_formula"),
                "lower_bound_formula": row.get("lower_bound_formula"),
                "duration_adjusted_formula": row.get("duration_adjusted_formula"),
                "batch_index": row.get("batch_index"),
            }
        )

    if dump_dir:
        dump_json(dump_dir / "ttwid-check.json", warmup)
        dump_json(dump_dir / "selected-playlets.json", selected_payload)
        dump_json(dump_dir / "completion-rank-batches.json", raw_batches)

    return {
        "count": len(merged_rows),
        "range": {
            "start_date": start_date,
            "end_date": end_date,
        },
        "metric_keys": {
            "total_play_count": TOTAL_METRIC_KEY,
            "avg_play_episodes_per_viewer": AVG_PLAY_EPISODES_METRIC_KEY,
            "playlet_duration_min": PLAYLET_DURATION_METRIC_KEY,
            "first_episode_finish_progress_pct": FIRST_EPISODE_PROGRESS_KEY,
            "finish_10min_rate_pct": FINISH_10MIN_KEY,
            "finish_30min_rate_pct": FINISH_30MIN_KEY,
            "finish_60min_rate_pct": FINISH_60MIN_KEY,
            "avg_episode_progress_pct": EPISODE_PROGRESS_SERIES_KEY,
            "avg_episode_continue_pct": EPISODE_CONTINUE_SERIES_KEY,
        },
        "rows": merged_rows,
        "warnings": [
            warning
            for warning in [
                "estimated_effective_play_minutes is a derived estimate, not a platform-native metric",
                "lower_bound_effective_minutes is a conservative floor derived from 10/30/60-minute completion buckets",
            ]
            if warning
        ],
    }


def handle_revenue_report(args: argparse.Namespace, client: CopyrightMetricsClient, dump_dir: Path | None) -> dict[str, Any]:
    completion_payload = handle_all_completion(args, client, dump_dir)
    rows = completion_payload["rows"]
    settlement_window = None
    if args.settlement_start_date or args.settlement_end_date:
        if not args.settlement_start_date or not args.settlement_end_date:
            raise ConfigError("settlement window requires both --settlement-start-date and --settlement-end-date")
        if not coerce_yyyymmdd(args.settlement_start_date):
            raise ConfigError(f"invalid settlement start date: {args.settlement_start_date}")
        if not coerce_yyyymmdd(args.settlement_end_date):
            raise ConfigError(f"invalid settlement end date: {args.settlement_end_date}")
        settlement_start_date = coerce_yyyymmdd(args.settlement_start_date)
        settlement_end_date = coerce_yyyymmdd(args.settlement_end_date)
        settlement_window = {
            "start_date": settlement_start_date,
            "end_date": settlement_end_date,
            "metric_key": args.settlement_metric_key,
        }
        for row in rows:
            trend_payload = client.fetch_trend(
                str(row.get("playlet_id")),
                settlement_start_date,
                settlement_end_date,
                args.settlement_metric_key,
            )
            settlement_play_count = extract_metric_sum(trend_payload, args.settlement_metric_key)
            row["settlement_play_count"] = settlement_play_count
            settlement_effective = derive_effective_minutes_for_play_count(row, to_float(settlement_play_count))
            row["settlement_estimated_effective_minutes"] = settlement_effective["estimated_effective_minutes"]
            row["settlement_estimated_effective_hours"] = settlement_effective["estimated_effective_hours"]
            row["settlement_lower_bound_effective_minutes"] = settlement_effective["lower_bound_effective_minutes"]
            row["settlement_lower_bound_effective_hours"] = settlement_effective["lower_bound_effective_hours"]
            row["settlement_duration_adjusted_effective_minutes"] = settlement_effective[
                "duration_adjusted_effective_minutes"
            ]
            row["settlement_duration_adjusted_effective_hours"] = settlement_effective[
                "duration_adjusted_effective_hours"
            ]
            row["settlement_effective_formula"] = (
                "settlement_play_count scaled through the same duration-adjusted effective-hours formula"
            )

    benchmark_row = resolve_report_row(
        rows,
        title=args.benchmark_title,
        playlet_id=args.benchmark_playlet_id,
    )
    basis_key = args.revenue_basis or (
        "settlement_duration_adjusted_effective_hours"
        if settlement_window
        else "duration_adjusted_effective_hours"
    )
    benchmark_basis_value = to_float(benchmark_row.get(basis_key))
    benchmark_revenue = float(args.benchmark_revenue)
    if benchmark_basis_value is None or benchmark_basis_value <= 0:
        raise ConfigError(f"benchmark row has no usable basis value for {basis_key}")

    lower_bound_benchmark_value = to_float(benchmark_row.get("lower_bound_effective_hours"))
    duration_adjusted_benchmark_value = to_float(benchmark_row.get("duration_adjusted_effective_hours"))
    settlement_lower_bound_benchmark_value = to_float(benchmark_row.get("settlement_lower_bound_effective_hours"))
    settlement_duration_adjusted_benchmark_value = to_float(
        benchmark_row.get("settlement_duration_adjusted_effective_hours")
    )

    report_rows: list[dict[str, Any]] = []
    for row in rows:
        basis_value = to_float(row.get(basis_key))
        revenue_multiplier = None
        estimated_revenue = None
        if basis_value is not None:
            revenue_multiplier = basis_value / benchmark_basis_value
            estimated_revenue = benchmark_revenue * revenue_multiplier
        lower_bound_revenue = None
        lower_bound_basis = to_float(row.get("lower_bound_effective_hours"))
        if lower_bound_basis is not None and lower_bound_benchmark_value:
            lower_bound_revenue = benchmark_revenue * lower_bound_basis / lower_bound_benchmark_value
        duration_adjusted_revenue = None
        duration_adjusted_basis = to_float(row.get("duration_adjusted_effective_hours"))
        if duration_adjusted_basis is not None and duration_adjusted_benchmark_value:
            duration_adjusted_revenue = benchmark_revenue * duration_adjusted_basis / duration_adjusted_benchmark_value
        settlement_lower_bound_revenue = None
        settlement_lower_bound_basis = to_float(row.get("settlement_lower_bound_effective_hours"))
        if settlement_lower_bound_basis is not None and settlement_lower_bound_benchmark_value:
            settlement_lower_bound_revenue = (
                benchmark_revenue * settlement_lower_bound_basis / settlement_lower_bound_benchmark_value
            )
        settlement_duration_adjusted_revenue = None
        settlement_duration_adjusted_basis = to_float(row.get("settlement_duration_adjusted_effective_hours"))
        if settlement_duration_adjusted_basis is not None and settlement_duration_adjusted_benchmark_value:
            settlement_duration_adjusted_revenue = (
                benchmark_revenue
                * settlement_duration_adjusted_basis
                / settlement_duration_adjusted_benchmark_value
            )
        report_rows.append(
            {
                **row,
                "revenue_basis": basis_key,
                "revenue_basis_value": basis_value,
                "benchmark_revenue": benchmark_revenue,
                "benchmark_title": benchmark_row.get("title"),
                "benchmark_playlet_id": benchmark_row.get("playlet_id"),
                "benchmark_basis_value": benchmark_basis_value,
                "revenue_multiplier_vs_benchmark": revenue_multiplier,
                "estimated_revenue": estimated_revenue,
                "estimated_revenue_lower_bound": lower_bound_revenue,
                "estimated_revenue_duration_adjusted": duration_adjusted_revenue,
                "estimated_revenue_settlement_lower_bound": settlement_lower_bound_revenue,
                "estimated_revenue_settlement_duration_adjusted": settlement_duration_adjusted_revenue,
            }
        )

    return {
        "count": len(report_rows),
        "range": completion_payload["range"],
        "metric_keys": completion_payload["metric_keys"],
        "revenue_basis": basis_key,
        "settlement_window": settlement_window,
        "benchmark": {
            "title": benchmark_row.get("title"),
            "playlet_id": benchmark_row.get("playlet_id"),
            "known_revenue": benchmark_revenue,
            "basis_key": basis_key,
            "basis_value": benchmark_basis_value,
            "lower_bound_effective_hours": lower_bound_benchmark_value,
            "duration_adjusted_effective_hours": duration_adjusted_benchmark_value,
            "settlement_play_count": benchmark_row.get("settlement_play_count"),
            "settlement_lower_bound_effective_hours": settlement_lower_bound_benchmark_value,
            "settlement_duration_adjusted_effective_hours": settlement_duration_adjusted_benchmark_value,
        },
        "rows": report_rows,
        "warnings": completion_payload["warnings"],
    }


def maybe_write_output(path: str | None, payload: dict[str, Any]) -> None:
    if not path:
        return
    output_path = Path(path)
    if output_path.suffix.lower() == ".csv":
        rows = payload.get("rows")
        if not isinstance(rows, list):
            raise ConfigError("CSV export is only supported for commands that return a rows array")
        dump_csv(output_path, rows)
        return
    dump_json(output_path, payload)


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    dump_dir = Path(args.dump_response_dir) if args.dump_response_dir else None

    try:
        auth = load_json(args.auth)
        client = CopyrightMetricsClient(auth)
        if args.command == "list":
            result = handle_list(args, client, dump_dir)
        elif args.command == "all-totals":
            result = handle_all_totals(args, client, dump_dir)
        elif args.command == "all-completion":
            result = handle_all_completion(args, client, dump_dir)
        elif args.command == "revenue-report":
            result = handle_revenue_report(args, client, dump_dir)
        else:
            result = handle_total(args, client, dump_dir)
        maybe_write_output(args.output, result)
    except ConfigError as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False, indent=2))
        return 2
    except requests.HTTPError as exc:
        response = exc.response
        message = {
            "error": "http_error",
            "status_code": response.status_code if response is not None else None,
            "response_text": response.text[:1000] if response is not None else None,
        }
        print(json.dumps(message, ensure_ascii=False, indent=2))
        return 3
    except requests.RequestException as exc:
        print(json.dumps({"error": f"request_failed: {exc}"}, ensure_ascii=False, indent=2))
        return 4

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
