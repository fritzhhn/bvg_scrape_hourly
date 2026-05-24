"""Sozialpolitisch relevante Auswertungen aus Störungs-Snapshots."""

from __future__ import annotations

import math
import sqlite3
from collections import Counter
from typing import Any

# Näherung: Alexanderplatz / Berlin-Mitte
BERLIN_CENTER = (52.5208, 13.4095)

MODE_LABELS = {
    0: "Regional",
    1: "S-Bahn",
    2: "U-Bahn",
    3: "Tram",
    4: "Bus",
    5: "Fähre",
    6: "Ersatzverkehr",
}

# Bus/Tram oft stärker in Außenbezirken; U/S-Bahn Kern
PERIPHERAL_MODES = {"Bus", "Tram", "Ersatzverkehr"}
CORE_MODES = {"U-Bahn", "S-Bahn", "Regional"}


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * r * math.asin(math.sqrt(min(1.0, a)))


def _ring_label(km: float) -> str:
    if km < 4.0:
        return "Zentrum (<4 km)"
    if km < 7.5:
        return "Mittelring (4–7,5 km)"
    return "Außenstadt (>7,5 km)"


def _classify_cause(types: list[str], message_type: str | None) -> str:
    if message_type == "ELEVATOR":
        return "Barrierefreiheit (Aufzug)"
    blob = " ".join(types).lower()
    if any(x in blob for x in ("bau", "baustelle", "gleis", "straße")):
        return "Infrastruktur / Bau"
    if any(x in blob for x in ("verspät", "ausfall", "stör", "unterbrech", "entfall")):
        return "Betriebsstörung"
    if any(x in blob for x in ("aufzug", "fahrstuhl", "rollstuhl")):
        return "Barrierefreiheit"
    return "Sonstiges"


def empty_insights() -> dict[str, Any]:
    return {
        "ready": False,
        "narratives": [
            {
                "title": "Noch keine Auswertung",
                "text": "Nach dem ersten Scrape-Lauf erscheinen hier Kennzielen zu Barrierefreiheit, Außenstadt vs. Zentrum und chronischen Störungen.",
                "tone": "muted",
            }
        ],
        "kpis": [],
        "modeShare": [],
        "ringShare": [],
        "causeShare": [],
        "chronicLeaders": [],
        "elevatorHotspots": [],
    }


def compute_insights(
    conn: sqlite3.Connection,
    *,
    snapshot_id: int,
    disruptions: list[dict[str, Any]],
    points: list[dict[str, Any]],
    history: dict[str, Any],
    comparison: dict[str, Any],
) -> dict[str, Any]:
    if not disruptions:
        return empty_insights()

    n = len(disruptions)
    traffic = sum(1 for d in disruptions if d.get("messageType") == "TRAFFIC")
    elevator = sum(1 for d in disruptions if d.get("messageType") == "ELEVATOR")
    scheduled = sum(1 for d in disruptions if d.get("scheduled"))

    mode_counts: Counter[str] = Counter()
    for d in disruptions:
        mode_counts[d.get("mode") or "Unbekannt"] += 1

    cause_counts: Counter[str] = Counter()
    for d in disruptions:
        cause_counts[_classify_cause(d.get("types") or [], d.get("messageType"))] += 1

    ring_counts: Counter[str] = Counter()
    station_ring: dict[str, str] = {}
    for p in points:
        km = _haversine_km(p["lat"], p["lon"], *BERLIN_CENTER)
        ring = _ring_label(km)
        ring_counts[ring] += 1
        station_ring[p.get("station") or ""] = ring

    total_pts = sum(ring_counts.values()) or 1
    ring_share = [
        {"ring": k, "count": v, "pct": round(100 * v / total_pts, 1)}
        for k, v in ring_counts.most_common()
    ]

    peripheral_n = sum(mode_counts.get(m, 0) for m in PERIPHERAL_MODES)
    core_n = sum(mode_counts.get(m, 0) for m in CORE_MODES)
    mode_total = sum(mode_counts.values()) or 1

    timeline = history.get("timeline") or []
    counts = [t.get("disruptions") or t.get("reported") or 0 for t in timeline]
    avg_hist = sum(counts) / len(counts) if counts else n
    pressure_pct = round(100 * (n - avg_hist) / avg_hist, 1) if avg_hist else 0

    registry_rows = conn.execute(
        """
        SELECT disruption_id, headline, hours_seen, days_seen, is_active,
               lines, station_one
        FROM disruption_registry
        """
    ).fetchall()
    chronic = [dict(r) for r in registry_rows if (r["days_seen"] or 0) >= 2 or (r["hours_seen"] or 0) >= 6]
    chronic_pct = round(100 * len(chronic) / max(1, len(registry_rows)), 1) if registry_rows else 0

    churn = (comparison.get("new_count") or 0) + (comparison.get("gone_count") or 0)
    churn_rate = round(100 * churn / max(1, n), 1) if comparison.get("prevHour") else None

    unique_lines = len({ln for d in disruptions for ln in (d.get("lines") or []) if ln})

    narratives: list[dict[str, str]] = []

    elev_pct = round(100 * elevator / n, 1)
    narratives.append(
        {
            "title": "Barrierefreiheit",
            "text": (
                f"{elev_pct}% der heutigen Meldungen betreffen Aufzüge ({elevator} von {n}). "
                "Ausfälle treffen Mobilitätseingeschränkte unmittelbar — oft ohne Alternative in der Station."
            ),
            "tone": "warn" if elev_pct >= 15 else "info",
        }
    )

    outer_pct = next((x["pct"] for x in ring_share if "Außenstadt" in x["ring"]), 0)
    inner_pct = next((x["pct"] for x in ring_share if "Zentrum" in x["ring"]), 0)
    narratives.append(
        {
            "title": "Zentrum vs. Außenstadt",
            "text": (
                f"Etwa {outer_pct}% der Kartenpunkte liegen im Außenbereich (>7,5 km vom Zentrum), "
                f"{inner_pct}% im engen Zentrum. "
                "Bus- und Tram-Störungen fallen statistisch häufiger in Randlagen an — "
                f"hier: {round(100*peripheral_n/mode_total,1)}% der Meldungen mit Schwerpunkt Bus/Tram/Ersatz."
            ),
            "tone": "highlight" if outer_pct > inner_pct + 10 else "info",
        }
    )

    if pressure_pct != 0 and len(counts) >= 2:
        narratives.append(
            {
                "title": "Systemdruck heute",
                "text": (
                    f"Aktuell {n} Meldungen (BVG „Heute“) — "
                    f"{'+' if pressure_pct > 0 else ''}{pressure_pct}% gegenüber dem Schnitt "
                    f"eurer bisherigen Snapshots ({round(avg_hist)}). "
                    "Hoher Druck bedeutet mehr gleichzeitige Unsicherheit im ÖPNV-Netz."
                ),
                "tone": "warn" if pressure_pct > 15 else "info",
            }
        )

    if churn_rate is not None:
        narratives.append(
            {
                "title": "Dynamik seit letztem Lauf",
                "text": (
                    f"Umschlag von {churn_rate}%: {comparison.get('new_count',0)} neu, "
                    f"{comparison.get('gone_count',0)} nicht mehr gelistet. "
                    "Hohe Fluktuation = wenig Planbarkeit für Pendler:innen."
                ),
                "tone": "warn" if churn_rate > 25 else "info",
            }
        )

    if chronic_pct > 0:
        narratives.append(
            {
                "title": "Chronische Störungen",
                "text": (
                    f"{chronic_pct}% der jemals erfassten Störungen waren mehrere Tage oder ≥6 Stunden sichtbar. "
                    "Langläufer belasten vor allem Viertel mit dauerhaften Baustellen oder defekten Aufzügen."
                ),
                "tone": "highlight",
            }
        )

    sched_pct = round(100 * scheduled / n, 1)
    narratives.append(
        {
            "title": "Geplant vs. akut",
            "text": (
                f"{sched_pct}% als geplant markiert (Baumaßnahmen etc.), Rest eher akut. "
                "Geplante Eingriffe sind kommunizierbar — ungeplante Störungen treffen überraschend."
            ),
            "tone": "info",
        }
    )

    kpis = [
        {"label": "Meldungen heute", "value": str(n), "hint": "wie bvg.de Heute"},
        {"label": "Betroffene Linien", "value": str(unique_lines), "hint": "einzelne Linienbezeichner"},
        {"label": "Aufzug / Barriere", "value": f"{elev_pct}%", "hint": f"{elevator} Meldungen"},
        {"label": "Außenstadt-Anteil", "value": f"{outer_pct}%", "hint": "Kartenpunkte >7,5 km"},
        {"label": "Chronisch (Historie)", "value": f"{chronic_pct}%", "hint": "≥2 Tage oder ≥6 Std."},
    ]
    if churn_rate is not None:
        kpis.append({"label": "Umschlag/Stunde", "value": f"{churn_rate}%", "hint": "neu + weg"})

    mode_share = [
        {"mode": m, "count": c, "pct": round(100 * c / mode_total, 1)}
        for m, c in mode_counts.most_common()
    ]

    cause_share = [{"cause": k, "count": v} for k, v in cause_counts.most_common()]

    chronic_leaders = sorted(
        [
            {
                "headline": r["headline"] or r["disruption_id"],
                "days": r["days_seen"],
                "hours": r["hours_seen"],
                "active": bool(r["is_active"]),
            }
            for r in registry_rows
            if (r["hours_seen"] or 0) >= 3
        ],
        key=lambda x: (x["days"], x["hours"]),
        reverse=True,
    )[:10]

    elev_stations: Counter[str] = Counter()
    for d in disruptions:
        if d.get("messageType") != "ELEVATOR":
            continue
        for key in ("stationOne", "stationTwo"):
            st = d.get(key)
            if st:
                elev_stations[st] += 1
    elevator_hotspots = [
        {"station": s, "count": c} for s, c in elev_stations.most_common(8)
    ]

    return {
        "ready": True,
        "narratives": narratives,
        "kpis": kpis,
        "modeShare": mode_share,
        "ringShare": ring_share,
        "causeShare": cause_share,
        "chronicLeaders": chronic_leaders,
        "elevatorHotspots": elevator_hotspots,
        "derived": {
            "elevatorSharePct": elev_pct,
            "outerSharePct": outer_pct,
            "peripheralModePct": round(100 * peripheral_n / mode_total, 1),
            "pressureVsAvgPct": pressure_pct,
            "chronicSharePct": chronic_pct,
        },
    }
