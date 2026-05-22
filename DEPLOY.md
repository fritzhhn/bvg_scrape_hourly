# Deploy: GitHub Actions (öffentliches Repo)

Für `fritzhhn/bvg_scrape_hourly` — Lauf alle **20 Minuten** ohne eigenen Server.

## Ist das ein Problem?

| Thema | Öffentliches Repo |
|--------|-------------------|
| **Kosten** | Actions-Minuten in der Regel **kostenlos** |
| **1 Jahr** | Ja, Schedule läuft dauerhaft |
| **SQLite** | Persistiert via **Actions Cache** (`data/disruptions.db`) |
| **Zeitplan** | **:00, :20, :40 Europe/Berlin** (`cron: "1,21,41 * * * *"` + `timezone`) |
| **Genauigkeit** | GitHub kann den Start um **5–15 Min** verschieben; an vollen UTC-Stunden ist die Last höher |
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

## Wenn `schedule` nicht startet (0 Läufe mit Event „schedule“)

Die Workflow-Datei ist korrekt ([GitHub-Doku: `schedule`](https://docs.github.com/en/actions/using-workflows/events-that-trigger-workflows#schedule)): nur auf **`main`**, min. alle 5 Min, optional `timezone: Europe/Berlin`.

**Geprüft auf diesem Repo:** `workflow_dispatch` und `repository_dispatch` laufen; **`schedule` hat bisher keinen einzigen Lauf ausgelöst** (auch kein Test mit `*/15 * * * *` UTC). Das ist kein lokales Script-Problem, sondern dass der **GitHub-Scheduler** das Repo noch nicht triggert (bei neuen Repos Berichten zufolge oft Stunden bis zum ersten Lauf; manchmal muss der Workflow in der UI reaktiviert werden).

**In der UI prüfen:** Actions → **BVG hourly scrape** → steht dort „Scheduled workflows disabled“ / **Enable workflow**?

**Fallback ohne Rechner bei dir (läuft trotzdem auf GitHub Actions):** kostenloser Dienst z. B. [cron-job.org](https://cron-job.org) alle 20 Min:

```http
POST https://api.github.com/repos/fritzhhn/bvg_scrape_hourly/dispatches
Authorization: Bearer <PAT mit repo scope>
Accept: application/vnd.github+json
Content-Type: application/json

{"event_type":"scrape"}
```

Der Workflow hat `repository_dispatch: types: [scrape]` — gleicher Ablauf wie manuell, nur extern getaktet.

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
