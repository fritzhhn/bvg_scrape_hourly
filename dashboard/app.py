"""Streamlit dashboard: Berlin disruption heatmap and temporal analysis."""

from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

import folium
import pandas as pd
import plotly.express as px
import streamlit as st
from folium.plugins import HeatMap
from streamlit_folium import st_folium

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "disruptions.db"

BERLIN_CENTER = [52.52, 13.405]
LINE_TYPE_LABELS = {
    0: "Regional",
    1: "S-Bahn",
    2: "U-Bahn",
    3: "Tram",
    4: "Bus",
    5: "Fähre",
    6: "Ersatzverkehr",
}


@st.cache_data(ttl=60)
def load_snapshots(db_path: str) -> pd.DataFrame:
    conn = sqlite3.connect(db_path)
    df = pd.read_sql_query(
        "SELECT id, collected_at, disruption_type, time_frame, total_found FROM snapshots ORDER BY collected_at DESC",
        conn,
    )
    conn.close()
    if not df.empty:
        df["collected_at"] = pd.to_datetime(df["collected_at"], utc=True)
    return df


@st.cache_data(ttl=60)
def load_disruptions(db_path: str, snapshot_id: int) -> pd.DataFrame:
    conn = sqlite3.connect(db_path)
    df = pd.read_sql_query(
        """
        SELECT d.*, p.station_name, p.lat, p.lon, p.resolved_name
        FROM disruptions d
        LEFT JOIN disruption_points p ON p.disruption_row_id = d.id
        WHERE d.snapshot_id = ?
        """,
        conn,
        params=(snapshot_id,),
    )
    conn.close()
    for col in ("start_date", "end_date", "mod_date"):
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce", utc=True)
    return df


@st.cache_data(ttl=60)
def load_snapshot_comparison(db_path: str) -> pd.DataFrame:
    conn = sqlite3.connect(db_path)
    df = pd.read_sql_query(
        """
        SELECT s.collected_at, s.id AS snapshot_id, d.disruption_id, d.message_type,
               d.disruption_types, d.lines, d.station_one, p.lat, p.lon
        FROM snapshots s
        JOIN disruptions d ON d.snapshot_id = s.id
        LEFT JOIN disruption_points p ON p.disruption_row_id = d.id
        WHERE p.lat IS NOT NULL
        """,
        conn,
    )
    conn.close()
    df["collected_at"] = pd.to_datetime(df["collected_at"], utc=True)
    return df


def build_heatmap(df: pd.DataFrame, weight_col: str | None = None) -> folium.Map:
    m = folium.Map(location=BERLIN_CENTER, zoom_start=11, tiles="CartoDB positron")
    points = df.dropna(subset=["lat", "lon"]).copy()
    if points.empty:
        folium.Marker(BERLIN_CENTER, popup="Keine geocodierten Haltestellen").add_to(m)
        return m

    if weight_col and weight_col in points.columns:
        heat_data = points[["lat", "lon", weight_col]].values.tolist()
    else:
        heat_data = points[["lat", "lon"]].values.tolist()

    HeatMap(heat_data, radius=18, blur=22, max_zoom=13).add_to(m)

    for _, row in points.drop_duplicates(subset=["lat", "lon"]).head(80).iterrows():
        folium.CircleMarker(
            location=[row["lat"], row["lon"]],
            radius=5,
            popup=f"{row.get('station_name') or row.get('station_one')}: {row.get('headline', '')}",
            color="#c41e3a",
            fill=True,
            fill_opacity=0.7,
        ).add_to(m)
    return m


def main() -> None:
    st.set_page_config(
        page_title="BVG Störungs-Dashboard",
        page_icon="🚇",
        layout="wide",
    )
    st.title("BVG Störungs-Dashboard")
    st.caption(
        "Daten von [bvg.de/stoerungsmeldungen](https://www.bvg.de/de/verbindungen/stoerungsmeldungen) "
        "via `/disruption-reports-service/disruptions/v1/de`"
    )

    if not DB_PATH.exists():
        st.warning(
            "Noch keine Daten. Einmal sammeln:\n\n"
            "```bash\npython -m collector.collect\nstreamlit run dashboard/app.py\n```"
        )
        if st.button("Jetzt Daten sammeln (dauert ~1–2 Min.)"):
            from collector.collect import run_collect

            with st.spinner("Lade Störungsmeldungen…"):
                run_collect(DB_PATH)
            st.rerun()
        return

    snapshots = load_snapshots(str(DB_PATH))
    if snapshots.empty:
        st.info("Datenbank leer – bitte Collector ausführen.")
        return

    with st.sidebar:
        st.header("Filter")
        snap_labels = [
            f"{row['collected_at'].strftime('%d.%m.%Y %H:%M')} UTC ({row['total_found']} Meldungen)"
            for _, row in snapshots.iterrows()
        ]
        snap_idx = st.selectbox("Snapshot", range(len(snap_labels)), format_func=lambda i: snap_labels[i])
        snapshot_id = int(snapshots.iloc[snap_idx]["id"])

        df = load_disruptions(str(DB_PATH), snapshot_id)

        msg_types = sorted(df["message_type"].dropna().unique())
        type_filter = st.multiselect("Meldungstyp", msg_types, default=msg_types)

        all_dtype = sorted({t.strip() for s in df["disruption_types"].dropna() for t in s.split(",") if t.strip()})
        dtype_filter = st.multiselect("Störungstyp", all_dtype, default=all_dtype)

        all_lines = sorted({l.strip() for s in df["lines"].dropna() for l in s.split(",") if l.strip()})
        line_filter = st.multiselect("Linie", all_lines, default=all_lines)

        only_geo = st.checkbox("Nur geocodierte Haltestellen", value=False)

    filtered = df[df["message_type"].isin(type_filter)].copy()
    if dtype_filter:
        filtered = filtered[
            filtered["disruption_types"].fillna("").apply(
                lambda s: any(t in s for t in dtype_filter)
            )
        ]
    if line_filter:
        filtered = filtered[
            filtered["lines"].fillna("").apply(lambda s: any(l in s for l in line_filter))
        ]
    if only_geo:
        filtered = filtered.dropna(subset=["lat", "lon"])

    geo = filtered.dropna(subset=["lat", "lon"])
    unique_disruptions = filtered.drop_duplicates(subset=["disruption_id"])

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Meldungen", len(unique_disruptions))
    c2.metric("Haltestellen-Punkte", len(geo))
    c3.metric("Verkehr", len(unique_disruptions[unique_disruptions["message_type"] == "TRAFFIC"]))
    c4.metric("Aufzug", len(unique_disruptions[unique_disruptions["message_type"] == "ELEVATOR"]))

    tab_map, tab_time, tab_lines, tab_compare, tab_table = st.tabs(
        ["Heatmap", "Zeit & Typ", "Linien", "Snapshot-Vergleich", "Rohdaten"]
    )

    with tab_map:
        st.subheader("Berlin Heatmap – Störungs-Hotspots")
        st.markdown(
            "Jeder Punkt ist eine betroffene Haltestelle. Die Heatmap zeigt räumliche Häufung; "
            "für **zeitliche** Muster brauchst du mehrere Snapshots (Collector regelmäßig laufen lassen)."
        )
        col_map, col_info = st.columns([2, 1])
        with col_map:
            st_folium(build_heatmap(geo), width=700, height=520, returned_objects=[])
        with col_info:
            st.markdown("**Top-Haltestellen (aktueller Snapshot)**")
            top_stations = (
                geo.groupby("station_name")
                .size()
                .reset_index(name="count")
                .sort_values("count", ascending=False)
                .head(12)
            )
            st.dataframe(top_stations, hide_index=True, use_container_width=True)

    with tab_time:
        st.subheader("Wann treten Störungen auf?")
        u = unique_disruptions.copy()
        u["start_hour"] = u["start_date"].dt.hour
        u["weekday"] = u["start_date"].dt.day_name()
        u["mod_hour"] = u["mod_date"].dt.hour

        left, right = st.columns(2)
        with left:
            if u["start_date"].notna().any():
                fig = px.histogram(
                    u.dropna(subset=["start_date"]),
                    x="start_date",
                    color="message_type",
                    title="Startdatum der Meldungen",
                    labels={"start_date": "Start"},
                )
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("Keine Startdaten in diesem Snapshot.")

        with right:
            if u["mod_date"].notna().any():
                fig2 = px.histogram(
                    u.dropna(subset=["mod_date"]),
                    x="mod_hour",
                    color="message_type",
                    title="Stunde der letzten Änderung (mod_date)",
                    labels={"mod_hour": "Stunde (UTC)"},
                    nbins=24,
                )
                st.plotly_chart(fig2, use_container_width=True)

        st.markdown("**Störungstypen**")
        type_rows = []
        for _, row in u.iterrows():
            for t in (row["disruption_types"] or "").split(", "):
                if t:
                    type_rows.append({"type": t, "message_type": row["message_type"]})
        if type_rows:
            type_df = pd.DataFrame(type_rows)
            fig3 = px.bar(
                type_df["type"].value_counts().reset_index(),
                x="count",
                y="type",
                orientation="h",
                title="Häufigkeit nach Störungstyp",
                labels={"count": "Anzahl", "type": "Typ"},
            )
            fig3.update_layout(yaxis={"categoryorder": "total ascending"})
            st.plotly_chart(fig3, use_container_width=True)

    with tab_lines:
        st.subheader("Welche Linien sind betroffen?")
        line_rows = []
        for _, row in u.iterrows():
            for line in (row["lines"] or "").split(", "):
                if line:
                    line_rows.append({"line": line, "message_type": row["message_type"]})
        if line_rows:
            line_df = pd.DataFrame(line_rows)
            fig4 = px.bar(
                line_df["line"].value_counts().head(25).reset_index(),
                x="count",
                y="line",
                orientation="h",
                color="count",
                title="Top 25 betroffene Linien",
            )
            fig4.update_layout(yaxis={"categoryorder": "total ascending"}, showlegend=False)
            st.plotly_chart(fig4, use_container_width=True)

        u["mode"] = u["first_line_type"].map(LINE_TYPE_LABELS).fillna("Unbekannt")
        fig5 = px.pie(u, names="mode", title="Verkehrsmittel (first_line_type)")
        st.plotly_chart(fig5, use_container_width=True)

    with tab_compare:
        st.subheader("Snapshot-Vergleich (Zeitreihe)")
        hist = load_snapshot_comparison(str(DB_PATH))
        if hist["snapshot_id"].nunique() < 2:
            st.info(
                "Nur ein Snapshot vorhanden. Für Zeitanalysen den Collector regelmäßig ausführen, z. B.:\n\n"
                "```bash\n# alle 15 Minuten\ncrontab -e\n*/15 * * * * cd /pfad/zum/projekt && python -m collector.collect\n```"
            )
            ts = (
                hist.groupby(hist["collected_at"].dt.floor("h"))
                .size()
                .reset_index(name="points")
            )
            if not ts.empty:
                st.plotly_chart(
                    px.line(ts, x="collected_at", y="points", title="Punkte pro Snapshot-Zeit"),
                    use_container_width=True,
                )
        else:
            ts = hist.groupby("collected_at").agg(
                disruptions=("disruption_id", "nunique"),
                points=("lat", "count"),
            ).reset_index()
            st.plotly_chart(
                px.line(ts, x="collected_at", y=["disruptions", "points"], title="Entwicklung über Snapshots"),
                use_container_width=True,
            )

            latest = hist["collected_at"].max()
            previous = hist[hist["collected_at"] < latest]["collected_at"].max()
            if pd.notna(previous):
                cur_ids = set(hist[hist["collected_at"] == latest]["disruption_id"])
                prev_ids = set(hist[hist["collected_at"] == previous]["disruption_id"])
                new_ids = cur_ids - prev_ids
                gone_ids = prev_ids - cur_ids
                st.markdown(
                    f"**Neu** seit letztem Snapshot: {len(new_ids)} · **Beendet/weg**: {len(gone_ids)}"
                )
                if new_ids:
                    new_df = hist[
                        (hist["collected_at"] == latest) & (hist["disruption_id"].isin(new_ids))
                    ].drop_duplicates("disruption_id")[["disruption_id", "station_one", "lines", "disruption_types"]]
                    st.dataframe(new_df.head(20), hide_index=True)

    with tab_table:
        show = unique_disruptions[
            [
                "headline",
                "disruption_types",
                "lines",
                "station_one",
                "station_two",
                "start_date",
                "end_date",
                "message_type",
            ]
        ].sort_values("start_date", ascending=False)
        st.dataframe(show, hide_index=True, use_container_width=True)


if __name__ == "__main__":
    main()
