# BVG Störungs-Dashboard

Sammelt **alle Felder** der BVG-Störungsmeldungen (vollständiges JSON) und vergleicht **stündlich**, was neu ist, weg ist oder sich geändert hat.

## API

```
GET https://www.bvg.de/disruption-reports-service/disruptions/v1/de
    ?type=all&timeFrame=TODAY&page=1
```

Pro Meldung wird gespeichert: `raw_json` (komplettes API-JSON) plus alle Felder einzeln (`content_json`, `images_json`, `individualDisruptions`, `bahnhofHafasId`, Richtungen, …).

## Setup

```bash
cd "bvg scrape"
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

## Stündlicher Lauf (Standard)

```bash
python -m collector.hourly
python dashboard/build_html.py   # optional, auch alle 6h automatisch
open dashboard/index.html
```

Cron — **jede Stunde** (VPS):

```cron
0 * * * * /path/to/bvg_scrape_hourly/scripts/hourly.sh
```

### GitHub Actions (öffentliches Repo, z. B. `fritzhhn/bvg_scrape_hourly`)

Kein Server nötig — Workflow `.github/workflows/hourly.yml` (Cache für SQLite, Pages für Dashboard).  
Details: **[DEPLOY.md](DEPLOY.md)** · 1 Tag testen: Actions → **Run workflow** 2× mit `force`.

## Dauer & Speicher (1 Jahr)

| | Wert |
|---|---|
| **Dauer/Lauf** | ~1–3 s (API + DB, Geocode aus Cache) |
| **Daten/Lauf** | ~108 Meldungen × vollständiges JSON (~200–400 KB Snapshot) |
| **1 Jahr** | 365 × 24 ≈ **8.760 Läufe** → ca. **500 MB–2 GB** SQLite |

Das Dashboard wird nach **jedem** stündlichen Lauf neu gebaut und auf GitHub Pages deployed.

## Was wird verglichen?

- **Neu** – ID war in der letzten Stunde nicht da  
- **Weg** – ID fehlt jetzt  
- **Geändert** – gleiche ID, aber `modDate` anders  
- **hours_seen** – wie viele Stunden eine Meldung mindestens sichtbar war  

## Projektstruktur

- `collector/hourly.py` – geplanter Cron-Lauf  
- `collector/normalize.py` – alle JSON-Felder  
- `data/disruptions.db` – Historie (gitignored)  
- `dashboard/index.html` – statisches Dashboard  
