"""Flatten BVG disruption JSON — all fields from the API response."""

from __future__ import annotations

import json
import re
from html import unescape
from typing import Any

LINE_MODES = ("subway", "sbahn", "tram", "bus", "ferry", "regional", "replacement")


def strip_html(text: str) -> str:
    text = unescape(text or "")
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def json_dumps(obj: Any) -> str | None:
    if obj is None:
        return None
    return json.dumps(obj, ensure_ascii=False)


def station_name(station: dict[str, Any] | None) -> str | None:
    if not station:
        return None
    return station.get("displayName")


def extract_lines(lines_field: list[dict[str, Any]] | None) -> list[str]:
    names: list[str] = []
    if not lines_field:
        return names
    for group in lines_field:
        for mode in LINE_MODES:
            for line in group.get(mode) or []:
                name = line.get("name")
                if name:
                    names.append(name)
    return names


def extract_disruption_types(types_field: list[dict[str, Any]] | None) -> list[str]:
    if not types_field:
        return []
    return [t.get("displayName", "") for t in types_field if t.get("displayName")]


def normalize_disruption(raw: dict[str, Any]) -> dict[str, Any]:
    """Map every top-level JSON field; store full payload in raw_json."""
    content_list = raw.get("content") or []
    primary = content_list[0] if content_list else {}
    types = extract_disruption_types(raw.get("disruptionTypes"))
    lines = extract_lines(raw.get("lines"))

    stations = []
    for key in ("stationOne", "stationTwo", "stationThree"):
        name = station_name(raw.get(key))
        if name:
            stations.append(name)

    message_category = raw.get("messageCategory")
    if isinstance(message_category, list):
        category_str = ", ".join(str(c) for c in message_category)
    elif message_category is not None:
        category_str = str(message_category)
    else:
        category_str = None

    return {
        "disruption_id": str(raw.get("id", "")),
        "message_type": raw.get("messageType"),
        "message_category": category_str,
        "message_category_json": json_dumps(message_category),
        "disruption_types": types,
        "disruption_types_str": ", ".join(types),
        "disruption_types_json": json_dumps(raw.get("disruptionTypes")),
        "lines": lines,
        "lines_str": ", ".join(lines),
        "lines_json": json_dumps(raw.get("lines")),
        "station_one": station_name(raw.get("stationOne")),
        "station_two": station_name(raw.get("stationTwo")),
        "station_three": station_name(raw.get("stationThree")),
        "station_one_json": json_dumps(raw.get("stationOne")),
        "station_two_json": json_dumps(raw.get("stationTwo")),
        "station_three_json": json_dumps(raw.get("stationThree")),
        "bahnhof_hafas_id": raw.get("bahnhofHafasId"),
        "direction_one": raw.get("directionOne"),
        "direction_two": raw.get("directionTwo"),
        "headline": primary.get("headline"),
        "summary": strip_html(primary.get("content", ""))[:2000],
        "content_html": primary.get("content"),
        "content_icon": primary.get("icon"),
        "content_json": json_dumps(content_list),
        "images_json": json_dumps(raw.get("images")),
        "individual_disruptions_json": json_dumps(raw.get("individualDisruptions")),
        "start_date": raw.get("startDate"),
        "end_date": raw.get("endDate"),
        "mod_date": raw.get("modDate"),
        "hide_time": 1 if raw.get("hideTime") else 0,
        "show_on_startpage": 1 if raw.get("showOnStartpage") else 0,
        "scheduled": 1 if raw.get("scheduled") else 0,
        "first_line_type": raw.get("firstLineLineType"),
        "raw_json": json_dumps(raw),
        "stations": stations,
    }
