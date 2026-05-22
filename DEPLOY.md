# Deploy: GitHub Actions (öffentliches Repo)

Für `fritzhhn/bvg_scrape_hourly` — stündlicher Lauf ohne eigenen Server.

## Ist das ein Problem?

| Thema | Öffentliches Repo |
|--------|-------------------|
| **Kosten** | Actions-Minuten in der Regel **kostenlos** |
| **1 Jahr** | Ja, Schedule läuft dauerhaft |
| **SQLite** | Persistiert via **Actions Cache** (`data/disruptions.db`) |
| **Zeitplan** | Jede volle Stunde **:00 Europe/Berlin** (`timezone` im Workflow) |
| **Genauigkeit** | GitHub kann den Start um **5–15 Min** verschieben |
| **Backup** | Sonntags Artifact (90 Tage); für 1 Jahr ggf. zusätzlich manuell sichern |

Cache wird bei **stündlichem** Zugriff nicht wegen Inaktivität gelöscht (7-Tage-Regel gilt nur ohne Zugriff).

## Einen Tag testen

1. Repo auf GitHub anlegen (public): `bvg_scrape_hourly`
2. Diesen Ordner pushen (inkl. `.github/workflows/hourly.yml`)
3. **Settings → Actions → General →** Workflow permissions: **Read and write**
4. **Settings → Pages →** Source: **Deploy from branch** → Branch: `gh-pages` / root  
   (erscheint nach dem ersten erfolgreichen Lauf)
5. **Actions** → Workflow **BVG hourly scrape** → **Run workflow** (manuell, optional `force`)
6. Nach 2–3 Läufen: Pages-URL `https://fritzhhn.github.io/bvg_scrape_hourly/` (wenn `index.html` im dashboard-Ordner deployed wird)

Für einen schnellen Test ohne 1 Stunde warten: mehrfach **Run workflow** klicken (mit `force`), oder Schedule temporär auf `*/15 * * * *` stellen und nach dem Test zurück auf `0 * * * *`.

## Lokal → GitHub

```bash
cd "/Users/fritz/bvg scrape"
git init
git remote add origin git@github.com:fritzhhn/bvg_scrape_hourly.git
git add .
git commit -m "BVG hourly scrape with GitHub Actions"
git push -u origin main
```

Falls die DB schon lokal existiert und du die Historie mitnehmen willst:

```bash
# disruptions.db ist in .gitignore — einmalig für Cache-Seed:
# Ersten Workflow-Lauf mit force; danach Cache übernimmt.
```

Optional: erste DB in Repo **nicht** committen (zu groß, unnötig). Cache baut sich in wenigen Stunden auf.

## Cron manuell auslösen

Actions → **BVG hourly scrape** → **Run workflow**

## Alternative: Hetzner VPS

Siehe README — ein Cron auf dem Server ist einfacher für „eine Datei, ein Jahr“, wenn Actions-CACHE oder Pages stören.
