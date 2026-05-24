#!/usr/bin/env python3
"""Build standalone dashboard/index.html from the latest SQLite snapshot."""

from __future__ import annotations

import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from collector.db import connect
from collector.lifecycle import compare_snapshots, get_last_two_snapshots, load_history_stats, migrate
from dashboard.insights import compute_insights, empty_insights

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "disruptions.db"
OUT_PATH = Path(__file__).resolve().parent / "index.html"

LINE_TYPE_LABELS = {
    0: "Regional",
    1: "S-Bahn",
    2: "U-Bahn",
    3: "Tram",
    4: "Bus",
    5: "Fähre",
    6: "Ersatzverkehr",
}


def empty_payload() -> dict:
    now = datetime.now().astimezone().isoformat()
    return {
        "meta": {
            "collectedAt": None,
            "collectedDay": None,
            "collectedHour": None,
            "timeFrame": "TODAY",
            "disruptionType": "all",
            "numFound": 0,
            "generatedAt": now,
            "totalSnapshots": 0,
            "empty": True,
        },
        "disruptions": [],
        "points": [],
        "comparison": {
            "new": [],
            "gone": [],
            "modified": [],
            "new_count": 0,
            "gone_count": 0,
            "modified_count": 0,
            "continued_count": 0,
        },
        "history": {
            "totalSnapshots": 0,
            "uniqueDisruptionsEver": 0,
            "timeline": [],
            "longestVisible": [],
            "recentlyEnded": [],
        },
        "insights": empty_insights(),
    }


def load_payload(db_path: Path) -> dict:
    if not db_path.exists():
        return empty_payload()

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    snap = conn.execute(
        "SELECT * FROM snapshots ORDER BY collected_at DESC LIMIT 1"
    ).fetchone()
    if not snap:
        conn.close()
        return empty_payload()

    rows = conn.execute(
        """
        SELECT d.disruption_id, d.message_type, d.disruption_types, d.lines,
               d.station_one, d.station_two, d.headline, d.summary,
               d.start_date, d.end_date, d.mod_date, d.scheduled, d.first_line_type,
               p.station_name, p.lat, p.lon, p.resolved_name
        FROM disruptions d
        LEFT JOIN disruption_points p ON p.disruption_row_id = d.id
        WHERE d.snapshot_id = ?
        """,
        (snap["id"],),
    ).fetchall()
    conn.close()

    disruptions: dict[str, dict] = {}
    points: list[dict] = []
    for r in rows:
        did = r["disruption_id"]
        if did not in disruptions:
            disruptions[did] = {
                "id": did,
                "messageType": r["message_type"],
                "types": [t.strip() for t in (r["disruption_types"] or "").split(",") if t.strip()],
                "lines": [l.strip() for l in (r["lines"] or "").split(",") if l.strip()],
                "stationOne": r["station_one"],
                "stationTwo": r["station_two"],
                "headline": r["headline"],
                "summary": r["summary"],
                "startDate": r["start_date"],
                "endDate": r["end_date"],
                "modDate": r["mod_date"],
                "scheduled": bool(r["scheduled"]),
                "mode": LINE_TYPE_LABELS.get(r["first_line_type"], "Unbekannt"),
            }
        if r["lat"] is not None and r["lon"] is not None:
            points.append(
                {
                    "disruptionId": did,
                    "station": r["station_name"],
                    "lat": r["lat"],
                    "lon": r["lon"],
                    "resolvedName": r["resolved_name"],
                }
            )

    conn2 = connect(db_path)
    migrate(conn2)
    prev, curr = get_last_two_snapshots(conn2)
    comparison = {"new": [], "gone": [], "new_count": 0, "gone_count": 0, "continued_count": 0}
    if prev and curr:
        comparison = compare_snapshots(conn2, prev["id"], curr["id"])
        comparison["prevHour"] = prev["collected_hour"] or prev["collected_day"]
        comparison["currHour"] = curr["collected_hour"] or curr["collected_day"]
    history = load_history_stats(conn2)
    dis_list = list(disruptions.values())
    insights = compute_insights(
        conn2,
        snapshot_id=snap["id"],
        disruptions=dis_list,
        points=points,
        history=history,
        comparison=comparison,
    )
    conn2.close()

    return {
        "meta": {
            "collectedAt": snap["collected_at"],
            "collectedDay": snap["collected_day"] if "collected_day" in snap.keys() else None,
            "collectedHour": snap["collected_hour"] if "collected_hour" in snap.keys() else None,
            "timeFrame": snap["time_frame"],
            "disruptionType": snap["disruption_type"],
            "numFound": snap["total_found"],
            "generatedAt": datetime.now().astimezone().isoformat(),
            "totalSnapshots": history["totalSnapshots"],
        },
        "disruptions": list(disruptions.values()),
        "points": points,
        "comparison": comparison,
        "history": history,
        "insights": insights,
    }


HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="de">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>BVG Störungs-Dashboard</title>
  <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
  <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
  <script src="https://unpkg.com/leaflet.heat@0.2.0/dist/leaflet-heat.js"></script>
  <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
  <style>
    :root {
      --bvg: #f0d722;
      --bg: #0f1117;
      --card: #1a1d27;
      --text: #e8eaef;
      --muted: #9aa3b2;
      --accent: #c41e3a;
      --border: #2a3042;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: "Segoe UI", system-ui, sans-serif;
      background: var(--bg);
      color: var(--text);
      line-height: 1.45;
    }
    header {
      background: linear-gradient(135deg, #1a1d27 0%, #252a3a 100%);
      border-bottom: 3px solid var(--bvg);
      padding: 1.25rem 1.5rem 1rem;
    }
    header h1 { margin: 0 0 .25rem; font-size: 1.5rem; }
    header p { margin: 0; color: var(--muted); font-size: .9rem; }
    header a { color: var(--bvg); }
    .wrap { max-width: 1400px; margin: 0 auto; padding: 1rem 1.5rem 2rem; }
    .metrics {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
      gap: .75rem;
      margin-bottom: 1rem;
    }
    .metric {
      background: var(--card);
      border: 1px solid var(--border);
      border-radius: 10px;
      padding: .85rem 1rem;
    }
    .metric strong { display: block; font-size: 1.6rem; color: var(--bvg); }
    .metric span { font-size: .8rem; color: var(--muted); }
    .filters {
      display: flex; flex-wrap: wrap; gap: .75rem; align-items: end;
      background: var(--card); border: 1px solid var(--border);
      border-radius: 10px; padding: 1rem; margin-bottom: 1rem;
    }
    .filters label { display: flex; flex-direction: column; gap: .25rem; font-size: .8rem; color: var(--muted); }
    .filters select { min-width: 160px; padding: .4rem .5rem; border-radius: 6px; border: 1px solid var(--border); background: #12151c; color: var(--text); }
    .grid-main {
      display: grid;
      grid-template-columns: 1.4fr 1fr;
      gap: 1rem;
    }
    @media (max-width: 960px) { .grid-main { grid-template-columns: 1fr; } }
    .card {
      background: var(--card);
      border: 1px solid var(--border);
      border-radius: 10px;
      padding: 1rem;
      margin-bottom: 1rem;
    }
    .card h2 { margin: 0 0 .75rem; font-size: 1rem; }
    #map { height: 480px; border-radius: 8px; }
    .charts { display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; }
    @media (max-width: 720px) { .charts { grid-template-columns: 1fr; } }
    .chart-box { height: 260px; position: relative; }
    table { width: 100%; border-collapse: collapse; font-size: .85rem; }
    th, td { text-align: left; padding: .45rem .5rem; border-bottom: 1px solid var(--border); }
    th { color: var(--muted); font-weight: 600; }
    tr:hover td { background: #222633; }
    .badge { display: inline-block; padding: .1rem .45rem; border-radius: 4px; font-size: .72rem; background: #2d3548; margin-right: .25rem; }
    .badge.traffic { background: #3d2a14; color: #f5c26b; }
    .badge.elevator { background: #1e3a4a; color: #7ec8e3; }
    .note { font-size: .82rem; color: var(--muted); margin-top: .5rem; }
    .banner-empty {
      background: #2a3042;
      border: 1px solid var(--bvg);
      border-radius: 10px;
      padding: 1rem 1.25rem;
      margin-bottom: 1rem;
      color: var(--text);
    }
    .section-title {
      font-size: 1.15rem;
      margin: 0 0 .35rem;
      color: var(--bvg);
    }
    .section-lead {
      margin: 0 0 1rem;
      font-size: .88rem;
      color: var(--muted);
      max-width: 72ch;
    }
    .insight-narratives {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
      gap: .75rem;
      margin-bottom: 1rem;
    }
    .insight-card {
      background: #222633;
      border-left: 4px solid var(--bvg);
      border-radius: 8px;
      padding: .85rem 1rem;
    }
    .insight-card h3 { margin: 0 0 .4rem; font-size: .92rem; }
    .insight-card p { margin: 0; font-size: .84rem; color: #c8cdd8; }
    .insight-card.warn { border-left-color: var(--accent); }
    .insight-card.highlight { border-left-color: #6bc9a8; }
    .insight-card.muted { border-left-color: var(--muted); }
    .kpi-insights {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
      gap: .5rem;
      margin-bottom: 1rem;
    }
    .kpi-insights .metric strong { font-size: 1.25rem; }
  </style>
</head>
<body>
  <header>
    <h1>BVG Störungs-Dashboard</h1>
    <p>
      Daten wie auf
      <a href="https://www.bvg.de/de/verbindungen/stoerungsmeldungen" target="_blank" rel="noopener">bvg.de/stoerungsmeldungen</a>
      · Filter: <strong id="meta-filter"></strong> · Stand: <strong id="meta-time"></strong>
    </p>
  </header>
  <div class="wrap">
    <div id="empty-banner" class="banner-empty" style="display:none">
      Noch keine Scrape-Daten. Die Karte zeigt Berlin — nach dem ersten stündlichen Lauf (oder Actions-Run) erscheinen Störungen hier.
    </div>
    <div class="metrics" id="metrics"></div>

    <section class="card" id="insights-section">
      <h2 class="section-title">Mobilität &amp; Gerechtigkeit</h2>
      <p class="section-lead">
        Auswertung der BVG-Störungsmeldungen: Wer ist wie stark betroffen?
        Barrierefreiheit, Innen- vs. Außenstadt, Verkehrsmittel und Dauerbelastung — aus euren Scrape-Daten, nicht amtliche Sozialstatistik.
      </p>
      <div class="insight-narratives" id="insight-narratives"></div>
      <div class="kpi-insights" id="insight-kpis"></div>
      <div class="charts" style="margin-bottom:1rem">
        <div class="chart-box" style="height:240px"><canvas id="chart-rings"></canvas></div>
        <div class="chart-box" style="height:240px"><canvas id="chart-causes"></canvas></div>
        <div class="chart-box" style="height:240px"><canvas id="chart-mode-equity"></canvas></div>
      </div>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:1rem">
        <div>
          <h3 style="font-size:.9rem;margin:0 0 .5rem">Aufzug-Störungen nach Station</h3>
          <table><thead><tr><th>Station</th><th>#</th></tr></thead><tbody id="tbl-elevators"></tbody></table>
        </div>
        <div>
          <h3 style="font-size:.9rem;margin:0 0 .5rem">Langläufer (mehrere Tage sichtbar)</h3>
          <table><thead><tr><th>Meldung</th><th>Tage</th><th>Std.</th></tr></thead><tbody id="tbl-chronic"></tbody></table>
        </div>
      </div>
    </section>

    <div class="filters">
      <label>Meldungstyp
        <select id="f-type"><option value="">Alle</option></select>
      </label>
      <label>Störungstyp
        <select id="f-dtype"><option value="">Alle</option></select>
      </label>
      <label>Linie
        <select id="f-line"><option value="">Alle</option></select>
      </label>
    </div>
    <div class="grid-main">
      <div class="card">
        <h2>Berlin Heatmap</h2>
        <div id="map"></div>
        <p class="note">Heatmap = Häufung betroffener Haltestellen. Marker = einzelne Störungspunkte.</p>
      </div>
      <div>
        <div class="card">
          <h2>Top Haltestellen</h2>
          <table><thead><tr><th>Haltestelle</th><th>#</th></tr></thead><tbody id="top-stations"></tbody></table>
        </div>
        <div class="card">
          <h2>Neueste Meldungen</h2>
          <table><thead><tr><th>Meldung</th><th>Linie</th></tr></thead><tbody id="recent"></tbody></table>
        </div>
      </div>
    </div>
    <div class="card" id="history-section">
      <h2>Verlauf &amp; Tagesvergleich</h2>
      <p class="note" id="compare-note"></p>
      <div class="metrics" id="compare-metrics" style="margin-bottom:.75rem"></div>
      <div class="charts" style="grid-template-columns:1fr 1fr;margin-bottom:1rem">
        <div class="chart-box" style="height:220px"><canvas id="chart-timeline"></canvas></div>
        <div class="chart-box" style="height:220px"><canvas id="chart-duration"></canvas></div>
      </div>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:1rem">
        <div>
          <h3 style="font-size:.9rem;margin:0 0 .5rem;color:var(--bvg)">Neu seit letztem Lauf</h3>
          <table><thead><tr><th>Meldung</th><th>Linie</th></tr></thead><tbody id="tbl-new"></tbody></table>
        </div>
        <div>
          <h3 style="font-size:.9rem;margin:0 0 .5rem;color:var(--accent)">Nicht mehr gelistet</h3>
          <table><thead><tr><th>Meldung</th><th>Tage sichtbar</th></tr></thead><tbody id="tbl-gone"></tbody></table>
        </div>
      </div>
      <h3 style="font-size:.9rem;margin:1rem 0 .5rem">Längste Anzeigedauer (Stunden sichtbar)</h3>
      <table><thead><tr><th>Meldung</th><th>Std.</th><th>Tage</th><th>Erstmals</th><th>Zuletzt</th><th>Status</th></tr></thead><tbody id="tbl-longest"></tbody></table>
    </div>
    <div class="charts">
      <div class="card"><h2>Störungstypen</h2><div class="chart-box"><canvas id="chart-types"></canvas></div></div>
      <div class="card"><h2>Betroffene Linien</h2><div class="chart-box"><canvas id="chart-lines"></canvas></div></div>
      <div class="card"><h2>Verkehrsmittel</h2><div class="chart-box"><canvas id="chart-modes"></canvas></div></div>
      <div class="card"><h2>Start-Stunde (UTC)</h2><div class="chart-box"><canvas id="chart-hours"></canvas></div></div>
    </div>
    <div class="card">
      <h2>Alle Meldungen (<span id="table-count">0</span>)</h2>
      <div style="overflow-x:auto">
        <table>
          <thead>
            <tr><th>Headline</th><th>Typ</th><th>Linien</th><th>Station</th><th>Start</th></tr>
          </thead>
          <tbody id="all-rows"></tbody>
        </table>
      </div>
    </div>
  </div>
  <script id="dashboard-data" type="application/json">__DATA__</script>
  <script>
    const DATA = JSON.parse(document.getElementById("dashboard-data").textContent);
    const meta = DATA.meta;
    if (meta.empty) {
      document.getElementById("empty-banner").style.display = "block";
      document.getElementById("meta-time").textContent = "Warte auf ersten Scrape…";
      document.getElementById("meta-filter").textContent =
        `type=${meta.disruptionType}, timeFrame=${meta.timeFrame} · 0 Snapshots`;
    } else {
      document.getElementById("meta-time").textContent = new Date(meta.collectedAt).toLocaleString("de-DE");
      document.getElementById("meta-filter").textContent =
        `type=${meta.disruptionType}, timeFrame=${meta.timeFrame} (${meta.numFound} wie bvg.de) · ${meta.totalSnapshots||1} Snapshot(s)`;
    }

    let map, heatLayer, markers = [];
    let charts = {};

    function uniq(arr) { return [...new Set(arr)].sort(); }

    function initFilters() {
      const types = uniq(DATA.disruptions.map(d => d.messageType).filter(Boolean));
      const dtypes = uniq(DATA.disruptions.flatMap(d => d.types));
      const lines = uniq(DATA.disruptions.flatMap(d => d.lines));
      for (const [id, vals] of [["f-type", types], ["f-dtype", dtypes], ["f-line", lines]]) {
        const sel = document.getElementById(id);
        vals.forEach(v => {
          const o = document.createElement("option");
          o.value = v; o.textContent = v;
          sel.appendChild(o);
        });
        sel.addEventListener("change", refresh);
      }
    }

    function filtered() {
      const mt = document.getElementById("f-type").value;
      const dt = document.getElementById("f-dtype").value;
      const ln = document.getElementById("f-line").value;
      return DATA.disruptions.filter(d => {
        if (mt && d.messageType !== mt) return false;
        if (dt && !d.types.includes(dt)) return false;
        if (ln && !d.lines.includes(ln)) return false;
        return true;
      });
    }

    function filteredPoints(ids) {
      const set = new Set(ids);
      return DATA.points.filter(p => set.has(p.disruptionId));
    }

    function refresh() {
      const dis = filtered();
      const ids = dis.map(d => d.id);
      const pts = filteredPoints(ids);

      document.getElementById("metrics").innerHTML = `
        <div class="metric"><strong>${dis.length}</strong><span>Meldungen</span></div>
        <div class="metric"><strong>${pts.length}</strong><span>Kartenpunkte</span></div>
        <div class="metric"><strong>${dis.filter(d=>d.messageType==="TRAFFIC").length}</strong><span>Verkehr</span></div>
        <div class="metric"><strong>${dis.filter(d=>d.messageType==="ELEVATOR").length}</strong><span>Aufzug</span></div>
      `;

      updateMap(pts, dis);
      updateTables(dis, pts);
      updateCharts(dis);
    }

    function updateMap(pts, dis) {
      if (!map) {
        map = L.map("map").setView([52.52, 13.405], 11);
        L.tileLayer("https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png", {
          attribution: "&copy; OpenStreetMap, &copy; CARTO",
          maxZoom: 19
        }).addTo(map);
      }
      if (heatLayer) map.removeLayer(heatLayer);
      markers.forEach(m => map.removeLayer(m));
      markers = [];

      const heat = pts.map(p => [p.lat, p.lon, 0.7]);
      if (heat.length) {
        heatLayer = L.heatLayer(heat, { radius: 22, blur: 18, maxZoom: 14 });
        heatLayer.addTo(map);
      }
      const popupById = Object.fromEntries(dis.map(d => [d.id, d]));
      pts.forEach(p => {
        const d = popupById[p.disruptionId];
        const m = L.circleMarker([p.lat, p.lon], {
          radius: 6, color: "#c41e3a", fillColor: "#f0d722", fillOpacity: 0.85, weight: 2
        }).bindPopup(`<strong>${p.station}</strong><br>${d?.headline || ""}<br><small>${(d?.lines||[]).join(", ")}</small>`);
        m.addTo(map);
        markers.push(m);
      });
      if (pts.length) {
        const b = L.latLngBounds(pts.map(p => [p.lat, p.lon]));
        map.fitBounds(b.pad(0.12));
      }
    }

    function updateTables(dis, pts) {
      const stationCounts = {};
      pts.forEach(p => { stationCounts[p.station] = (stationCounts[p.station]||0)+1; });
      const top = Object.entries(stationCounts).sort((a,b)=>b[1]-a[1]).slice(0,12);
      document.getElementById("top-stations").innerHTML = top.map(([s,c]) =>
        `<tr><td>${s}</td><td>${c}</td></tr>`).join("") || "<tr><td colspan=2>—</td></tr>";

      const recent = [...dis].sort((a,b)=>(b.modDate||"").localeCompare(a.modDate||"")).slice(0,8);
      document.getElementById("recent").innerHTML = recent.map(d =>
        `<tr><td>${d.headline||"—"}</td><td>${d.lines.join(", ")||"—"}</td></tr>`).join("");

      document.getElementById("table-count").textContent = dis.length;
      document.getElementById("all-rows").innerHTML = dis.map(d => `
        <tr>
          <td>${d.headline||"—"}</td>
          <td>${d.types.map(t=>`<span class="badge">${t}</span>`).join("")}</td>
          <td>${d.lines.join(", ")||"—"}</td>
          <td>${[d.stationOne,d.stationTwo].filter(Boolean).join(" – ")||"—"}</td>
          <td>${d.startDate ? new Date(d.startDate).toLocaleString("de-DE") : "—"}</td>
        </tr>`).join("");
    }

    function countMap(items, keyFn) {
      const m = {};
      items.forEach(i => keyFn(i).forEach(k => { if(k) m[k]=(m[k]||0)+1; }));
      return Object.entries(m).sort((a,b)=>b[1]-a[1]);
    }

    function barChart(id, entries, label) {
      if (charts[id]) charts[id].destroy();
      const ctx = document.getElementById(id);
      charts[id] = new Chart(ctx, {
        type: "bar",
        data: {
          labels: entries.map(e=>e[0]),
          datasets: [{ label, data: entries.map(e=>e[1]), backgroundColor: "#f0d722aa", borderColor: "#f0d722", borderWidth: 1 }]
        },
        options: {
          indexAxis: "y",
          responsive: true,
          maintainAspectRatio: false,
          plugins: { legend: { display: false } },
          scales: {
            x: { ticks: { color: "#9aa3b2" }, grid: { color: "#2a3042" } },
            y: { ticks: { color: "#e8eaef", font: { size: 10 } }, grid: { display: false } }
          }
        }
      });
    }

    function updateCharts(dis) {
      barChart("chart-types", countMap(dis, d => d.types).slice(0,12), "Typen");
      barChart("chart-lines", countMap(dis, d => d.lines).slice(0,15), "Linien");
      barChart("chart-modes", Object.entries(
        dis.reduce((a,d)=>{a[d.mode]=(a[d.mode]||0)+1;return a;}, {})
      ).sort((a,b)=>b[1]-a[1]), "Modus");
      const hours = Array(24).fill(0);
      dis.forEach(d => {
        if (!d.startDate) return;
        hours[new Date(d.startDate).getUTCHours()]++;
      });
      if (charts["chart-hours"]) charts["chart-hours"].destroy();
      charts["chart-hours"] = new Chart(document.getElementById("chart-hours"), {
        type: "bar",
        data: {
          labels: hours.map((_,i)=>i+"h"),
          datasets: [{ data: hours, backgroundColor: "#c41e3a99" }]
        },
        options: {
          responsive: true, maintainAspectRatio: false,
          plugins: { legend: { display: false } },
          scales: {
            x: { ticks: { color: "#9aa3b2", maxTicksLimit: 12 }, grid: { color: "#2a3042" } },
            y: { ticks: { color: "#9aa3b2" }, grid: { color: "#2a3042" } }
          }
        }
      });
    }

    function renderHistory() {
      const cmp = DATA.comparison || {};
      const hist = DATA.history || {};
      const daysMap = Object.fromEntries(
        (hist.longestVisible||[]).map(r => [r.disruption_id, r.days_seen])
      );
      if (cmp.prevHour && cmp.currHour) {
        document.getElementById("compare-note").textContent =
          `Stundenvergleich: ${cmp.prevHour} → ${cmp.currHour}`;
        document.getElementById("compare-metrics").innerHTML = `
          <div class="metric"><strong>${cmp.new_count||0}</strong><span>Neu</span></div>
          <div class="metric"><strong>${cmp.gone_count||0}</strong><span>Weg</span></div>
          <div class="metric"><strong>${cmp.modified_count||0}</strong><span>Geändert</span></div>
          <div class="metric"><strong>${cmp.continued_count||0}</strong><span>Gleich</span></div>
          <div class="metric"><strong>${hist.uniqueDisruptionsEver||0}</strong><span>Unique gesamt</span></div>`;
      } else {
        document.getElementById("compare-note").textContent =
          "Erster Lauf – ab der nächsten Stunde Stundenvergleich.";
      }
      document.getElementById("tbl-new").innerHTML = (cmp.new||[]).slice(0,15).map(r =>
        `<tr><td>${r.headline||r.disruption_id}</td><td>${r.lines||"—"}</td></tr>`).join("")
        || "<tr><td colspan=2>—</td></tr>";
      document.getElementById("tbl-gone").innerHTML = (cmp.gone||[]).slice(0,15).map(r =>
        `<tr><td>${r.headline||r.disruption_id}</td><td>${daysMap[r.disruption_id]||"?"}</td></tr>`).join("")
        || "<tr><td colspan=2>—</td></tr>";
      document.getElementById("tbl-longest").innerHTML = (hist.longestVisible||[]).slice(0,20).map(r =>
        `<tr><td>${r.headline||r.disruption_id}</td><td>${r.hours_seen||"—"}</td><td>${r.days_seen||"—"}</td>
         <td>${r.first_seen_at?.slice(0,16)||"—"}</td><td>${r.last_seen_at?.slice(0,16)||"—"}</td>
         <td>${r.is_active ? "aktiv" : "beendet"}</td></tr>`).join("")
        || "<tr><td colspan=6>Noch keine Historie</td></tr>";

      const tl = hist.timeline || [];
      if (tl.length && charts["chart-timeline"] === undefined) {
        new Chart(document.getElementById("chart-timeline"), {
          type: "line",
          data: {
            labels: tl.map(t => t.collected_day),
            datasets: [{ label: "Meldungen/Tag", data: tl.map(t => t.disruptions),
              borderColor: "#f0d722", tension: 0.2 }]
          },
          options: { responsive: true, maintainAspectRatio: false,
            plugins: { legend: { display: false } },
            scales: { x: { ticks: { color: "#9aa3b2" } }, y: { ticks: { color: "#9aa3b2" } } } }
        });
      }
      const dur = (hist.longestVisible||[]).filter(r => r.days_seen > 0).slice(0,12);
      if (dur.length) {
        new Chart(document.getElementById("chart-duration"), {
          type: "bar",
          data: {
            labels: dur.map(r => (r.headline||"").slice(0,28)),
            datasets: [{ data: dur.map(r => r.days_seen), backgroundColor: "#c41e3a99" }]
          },
          options: { indexAxis: "y", responsive: true, maintainAspectRatio: false,
            plugins: { legend: { display: false } },
            scales: { x: { ticks: { color: "#9aa3b2" } }, y: { ticks: { color: "#e8eaef", font: { size: 9 } } } } }
        });
      }
    }

    function renderInsights() {
      const ins = DATA.insights || {};
      const narr = ins.narratives || [];
      document.getElementById("insight-narratives").innerHTML = narr.map(n => `
        <div class="insight-card ${n.tone||"info"}">
          <h3>${n.title}</h3>
          <p>${n.text}</p>
        </div>`).join("");

      const kpis = ins.kpis || [];
      document.getElementById("insight-kpis").innerHTML = kpis.map(k => `
        <div class="metric">
          <strong>${k.value}</strong>
          <span>${k.label}</span>
          <span style="font-size:.7rem;display:block;margin-top:.2rem;color:var(--muted)">${k.hint||""}</span>
        </div>`).join("");

      document.getElementById("tbl-elevators").innerHTML = (ins.elevatorHotspots||[]).map(r =>
        `<tr><td>${r.station}</td><td>${r.count}</td></tr>`).join("")
        || "<tr><td colspan=2>Keine Aufzug-Meldungen</td></tr>";

      document.getElementById("tbl-chronic").innerHTML = (ins.chronicLeaders||[]).map(r =>
        `<tr><td>${(r.headline||"").slice(0,48)}</td><td>${r.days}</td><td>${r.hours}</td></tr>`).join("")
        || "<tr><td colspan=3>Noch keine Langläufer in der Historie</td></tr>";

      if (ins.ringShare && ins.ringShare.length) {
        if (charts["chart-rings"]) charts["chart-rings"].destroy();
        charts["chart-rings"] = new Chart(document.getElementById("chart-rings"), {
          type: "doughnut",
          data: {
            labels: ins.ringShare.map(r => r.ring),
            datasets: [{
              data: ins.ringShare.map(r => r.count),
              backgroundColor: ["#f0d722cc", "#c41e3a99", "#6bc9a899", "#4a7ab8aa"]
            }]
          },
          options: {
            responsive: true, maintainAspectRatio: false,
            plugins: {
              title: { display: true, text: "Räumliche Last (Haltestellenpunkte)", color: "#9aa3b2", font: { size: 12 } },
              legend: { labels: { color: "#e8eaef" } }
            }
          }
        });
      }
      if (ins.causeShare && ins.causeShare.length) {
        barChart("chart-causes", ins.causeShare.map(c => [c.cause, c.count]).slice(0,8), "Ursachen");
        const ctx = document.getElementById("chart-causes");
        if (charts["chart-causes"]) {
          charts["chart-causes"].options.plugins.title = {
            display: true, text: "Ursachenkategorien (sozial relevant)", color: "#9aa3b2", font: { size: 12 }
          };
          charts["chart-causes"].update();
        }
      }
      if (ins.modeShare && ins.modeShare.length) {
        if (charts["chart-mode-equity"]) charts["chart-mode-equity"].destroy();
        charts["chart-mode-equity"] = new Chart(document.getElementById("chart-mode-equity"), {
          type: "bar",
          data: {
            labels: ins.modeShare.map(m => m.mode),
            datasets: [{
              label: "% der Meldungen",
              data: ins.modeShare.map(m => m.pct),
              backgroundColor: ins.modeShare.map(m =>
                ["Bus","Tram","Ersatzverkehr"].includes(m.mode) ? "#c41e3a99" : "#f0d722aa")
            }]
          },
          options: {
            responsive: true, maintainAspectRatio: false,
            plugins: {
              title: { display: true, text: "Last nach Verkehrsmittel (rot = oft Randnetz)", color: "#9aa3b2", font: { size: 12 } },
              legend: { display: false }
            },
            scales: {
              x: { ticks: { color: "#9aa3b2" }, grid: { color: "#2a3042" } },
              y: { max: 100, ticks: { color: "#9aa3b2", callback: v => v+"%" }, grid: { color: "#2a3042" } }
            }
          }
        });
      }
    }

    initFilters();
    refresh();
    renderHistory();
    renderInsights();
  </script>
</body>
</html>
"""


def main() -> None:
    payload = load_payload(DB_PATH)
    html = HTML_TEMPLATE.replace("__DATA__", json.dumps(payload, ensure_ascii=False))
    OUT_PATH.write_text(html, encoding="utf-8")
    print(f"Written {OUT_PATH} ({payload['meta']['numFound']} disruptions)")


if __name__ == "__main__":
    main()
