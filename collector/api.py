"""Client for the BVG disruption reports API (same XHR as stoerungsmeldungen page)."""

from __future__ import annotations

import time
from typing import Any

import requests

BASE_URL = "https://www.bvg.de/disruption-reports-service/disruptions/v1/de"
LOCATIONS_URL = "https://www.bvg.de/api/search/v1/locations/byName/de"

HEADERS = {
    "Accept": "application/json",
    "User-Agent": "bvg-disruption-dashboard/1.0 (research; polite)",
}


def fetch_disruptions(
    *,
    disruption_type: str = "all",
    time_frame: str = "TODAY",
    page: int = 1,
    line: str | None = None,
    session: requests.Session | None = None,
) -> dict[str, Any]:
    params: dict[str, str | int] = {
        "type": disruption_type,
        "timeFrame": time_frame,
        "page": page,
    }
    if line:
        params["line"] = line
    sess = session or requests.Session()
    resp = sess.get(BASE_URL, params=params, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    return resp.json()


def fetch_all_disruptions(
    *,
    disruption_type: str = "all",
    time_frame: str = "TODAY",
    line: str | None = None,
    pause_seconds: float = 0.3,
) -> list[dict[str, Any]]:
    session = requests.Session()
    first = fetch_disruptions(
        disruption_type=disruption_type,
        time_frame=time_frame,
        page=1,
        line=line,
        session=session,
    )
    elements = list(first.get("elements") or [])
    num_pages = int(first.get("numPages") or 1)
    for page in range(2, num_pages + 1):
        time.sleep(pause_seconds)
        data = fetch_disruptions(
            disruption_type=disruption_type,
            time_frame=time_frame,
            page=page,
            line=line,
            session=session,
        )
        elements.extend(data.get("elements") or [])
    return elements


def search_station(name: str, session: requests.Session | None = None) -> dict[str, float] | None:
    """Return lat/lon for a stop (HST) matching the disruption station name."""
    sess = session or requests.Session()
    resp = sess.get(
        LOCATIONS_URL,
        params={"input": name},
        headers=HEADERS,
        timeout=15,
    )
    resp.raise_for_status()
    results = resp.json()
    if not isinstance(results, list):
        return None
    query = name.lower()
    for item in results:
        if item.get("type") != "HST":
            continue
        stop_name = (item.get("name") or "").lower()
        if query in stop_name or stop_name.startswith(query):
            return {
                "lat": float(item["latitude"]),
                "lon": float(item["longitude"]),
                "stop_id": item.get("id"),
                "resolved_name": item.get("name"),
            }
    for item in results:
        if item.get("type") == "HST":
            return {
                "lat": float(item["latitude"]),
                "lon": float(item["longitude"]),
                "stop_id": item.get("id"),
                "resolved_name": item.get("name"),
            }
    return None
