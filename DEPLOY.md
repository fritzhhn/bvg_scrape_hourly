# Deploy: GitHub Actions (öffentliches Repo)

Für `fritzhhn/bvg_scrape_hourly` — **stündlicher** Lauf ohne eigenen Server.

## Ist das ein Problem?

| Thema | Öffentliches Repo |
|--------|-------------------|
| **Kosten** | Actions-Minuten in der Regel **kostenlos** |
| **1 Jahr** | Ja, Schedule läuft dauerhaft |
| **SQLite** | Persistiert via **Actions Cache** (`data/disruptions.db`) |
| **Zeitplan** | Jede volle Stunde **:00 Europe/Berlin** (`cron: "0 * * * *"` + `timezone`) |
| **Genauigkeit** | GitHub kann den Start um **5–15 Min** verschieben (oft an vollen UTC-Stunden) |
| **Backup** | Sonntags Artifact (90 Tage); für 1 Jahr ggf. zusätzlich manuell sichern |

Cache wird bei **stündlichem** Zugriff nicht wegen Inaktivität gelöscht (7-Tage-Regel gilt nur ohne Zugriff).

## Einen Tag testen

1. Repo auf GitHub anlegen (public): `bvg_scrape_hourly`
2. Diesen Ordner pushen (inkl. `.github/workflows/hourly.yml`)
3. **Settings → Actions → General →** Workflow permissions: **Read and write**
4. **Settings → Pages →** Build and deployment → Source: **GitHub Actions** (nicht „Deploy from branch: main“ — sonst siehst du nur die README)
5. **Actions** → Workflow **BVG hourly scrape** → **Run workflow** (manuell, optional `force`)
6. Nach erfolgreichem Lauf: **https://fritzhhn.github.io/bvg_scrape_hourly/** (Heatmap-Dashboard, nicht README-Text)

Für einen schnellen Test: **Run workflow** (optional `force`).

## Wenn `schedule` nicht startet

Viele Nutzer berichten, dass der **erste** Cron-Lauf bei neuen Repos **verzögert** ist (Minuten bis Stunden, vereinzelt länger) — siehe [DevOps Journal / Xebia](https://devopsjournal.io/blog/2022/08/12/workflows-not-starting). In der Actions-Liste fehlt oft ein „Uhr“-Icon; das ist normal.

**Repo-Settings (geprüft):** Actions erlaubt, Workflow-Permissions auf **Read and write** gestellt (`Settings → Actions → General`).

**Test-Repo:** https://github.com/fritzhhn/gh-schedule-test — minimaler `*/15 * * * *` Workflow nach Doku. Wenn dort `schedule`-Läufe erscheinen, der Haupt-Workflow aber nicht, liegt es am BVG-Repo; wenn nirgends, am GitHub-Konto/Scheduler.

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
