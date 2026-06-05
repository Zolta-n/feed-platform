# Synology NAS Deployment Guide

Deploy **feed-platform** to a Synology DS225+ with push-to-deploy automation, mirroring the
`reporting` app: `git push` → GitHub Actions builds the image → `ghcr.io` → **Watchtower** on the
NAS auto-restarts the container → **Cloudflare Tunnel** (`cloudflared`, already running) exposes it.

| What | Value |
|---|---|
| GitHub repo | `https://github.com/Zolta-n/feed-platform` |
| Deploy branch | `deploy` (GitHub Actions builds on every push to it) |
| Container image | `ghcr.io/zolta-n/feed-platform:latest` |
| App URL | `https://bbw.businessintels.com` |
| Host port | `8001` (8000 is the reporting app) |
| Container name | `feed-platform-app` |
| NAS local IP | `192.168.50.70` |
| Compose path (on NAS) | `/volume1/docker/feed-platform/` |
| DSM login | `znponty.cz5.quickconnect.to` |

> This app is a **Flask/WSGI** app served by **gunicorn** (`wsgi:application`). The daily pipeline
> runs via **DSM Task Scheduler** (`SCHEDULER_ENABLED=false`). `DEPLOY_PA.md` remains the
> PythonAnywhere alternative.

---

## How it works (steady state)

```
git push → deploy branch → GitHub Actions builds image → ghcr.io/zolta-n/feed-platform:latest
                                                       → Watchtower on NAS detects new image
                                                       → feed-platform-app restarts automatically
```

After the one-time setup below, **you only need to push to `deploy`.** Watchtower polls every
5 minutes, so the NAS picks up changes within ~5 minutes.

---

## One-time setup

### Step 1 — Trigger the first image build

Push the `deploy` branch (it carries the app code + the scaffolding in this repo):

```bash
git push -u origin deploy
```

GitHub → **Actions** tab → confirm "Build and Push Docker Image" shows a green tick.

### Step 2 — Make the GHCR package public

So Watchtower can pull without credentials:

1. Go to `https://github.com/Zolta-n/feed-platform/pkgs/container/feed-platform`
2. **Package settings** → **Danger Zone** → Change visibility → **Public** → confirm.

### Step 3 — Create the NAS app folder + `.env`

In **File Station** create `/volume1/docker/feed-platform/` and a `data/` subfolder inside it.
Upload `docker-compose.yml` (from this repo) into `/volume1/docker/feed-platform/`.

Create a file `/volume1/docker/feed-platform/.env` (NEVER committed) with:

```dotenv
ANTHROPIC_API_KEY=sk-ant-...
SESSION_SECRET=<paste output of: python3 -c "import secrets; print(secrets.token_hex(32))">
APPROVAL_SECRET=<paste a SECOND token_hex(32)>
RESEND_API_KEY=re_...            # leave blank for dev (magic links shown directly)
DEEPL_API_KEY=                   # blank → Haiku fallback for translation
APP_URL=https://bbw.businessintels.com
FEED_DIR=/app/feeds/brake-by-wire
DB_PATH=/app/data/niche.db
NICHE_DB_PATH=/app/data/niche.db
SCHEDULER_ENABLED=false
```

> **Why both `DB_PATH` and `NICHE_DB_PATH`?** `wsgi.py` reads `DB_PATH`; the CLI reads
> `NICHE_DB_PATH` (else defaults to an ephemeral in-container `niche.db`). Setting both points the
> web app *and* every CLI/scheduled run at the same persisted DB on the mounted volume.

Also set the feed's sender to a Resend-verified address in
`feeds/brake-by-wire/config.yaml` (`from_email: ...`) — otherwise digest sends are rejected.

### Step 4 — Watchtower (skip if already running)

If a Watchtower container already runs from the `reporting` deploy, **skip this** — it watches all
containers and will pick up `feed-platform-app` automatically.

Otherwise: Container Manager → **Project → Create**, name `watchtower`, paste the contents of
`watchtower-compose.yml` from this repo, leave Web portal settings unchecked, **Done**.

### Step 5 — Create the feed-platform project

Container Manager → **Project → Create**:
- Name: `feed-platform`
- Path: `/volume1/docker/feed-platform`
- Source: the uploaded `docker-compose.yml`
- Web portal settings: leave unchecked → **Done**

Verify the container shows **Running**, then on the LAN open `http://192.168.50.70:8001` — you
should see the login page.

### Step 6 — Add the Cloudflare public hostname route

`cloudflared` is already running. In one.dash.cloudflare.com → **Networks → Connectors** →
`Synology-nas` → **Published application routes** → **Add a published application route**:

| Field | Value |
|---|---|
| Subdomain | `bbw` |
| Domain | `businessintels.com` |
| Path | (empty) |
| Type | `HTTP` |
| URL | `192.168.50.70:8001` |

Save. (If it complains about an existing A/CNAME record for `bbw`, delete it in Cloudflare
DNS → Records first.)

### Step 7 — Promote your admin user (one-time)

```bash
docker exec feed-platform-app python cli.py admin promote \
  --email you@example.com \
  --feed-dir /app/feeds/brake-by-wire \
  --db-path /app/data/niche.db
```

### Step 8 — First pipeline run (verify)

```bash
docker exec feed-platform-app python cli.py pipeline run \
  --feed-dir /app/feeds/brake-by-wire \
  --db-path /app/data/niche.db
```

Expect a JSON summary ending with `"status": "complete"`.

### Step 9 — Schedule the daily run (DSM Task Scheduler)

The in-process APScheduler stays disabled (`SCHEDULER_ENABLED=false`); use DSM's host-native cron.

DSM → **Control Panel → Task Scheduler → Create → Scheduled Task → User-defined script**.
Run as a user in the `docker` group, daily at your chosen local time (DSM uses the **NAS local
timezone** — no UTC conversion needed, unlike PythonAnywhere). Command:

```bash
docker exec feed-platform-app python cli.py pipeline run \
  --feed-dir /app/feeds/brake-by-wire \
  --db-path /app/data/niche.db \
  >> /volume1/docker/feed-platform/pipeline_cron.log 2>&1
```

> The `--db-path` flag is **required** here — without it the scheduled run would write to a
> throwaway DB inside the container instead of the persisted volume.

### Step 10 — Verify remote access

On a mobile device using **mobile data** (not WiFi), open `https://bbw.businessintels.com`:
- ✓ login page loads
- ✓ valid HTTPS padlock
- ✓ no port number in the URL

---

## Updating the app

Just push code to the `deploy` branch:

```bash
git checkout deploy
git merge <your-dev-branch>      # bring in new work
git push origin deploy
```

GitHub Actions rebuilds the image; Watchtower redeploys the container within ~5 minutes.
Nothing to do on the NAS.

---

## Troubleshooting

| Problem | Fix |
|---|---|
| Actions build fails | Open the failed job log. Common cause: a dependency that needs build tools — add `build-essential libxml2-dev libxslt1-dev` via `apt-get` in the Dockerfile (not normally needed for the pinned wheels). |
| Watchtower can't pull | GHCR package must be **Public** (Step 2). |
| `502 Bad Gateway` | Container not running — Container Manager → check `feed-platform-app`; verify `http://192.168.50.70:8001` works on the LAN. |
| App loads but data resets after restart | The `./data` volume mount or `DB_PATH`/`NICHE_DB_PATH` is wrong — both must point at `/app/data/niche.db` (Step 3). |
| Digest emails not sent | `from_email` in `config.yaml` must match a Resend-verified domain; `RESEND_API_KEY` set in `.env`. |
| DNS conflict on Cloudflare save | Delete the old A record for `bbw` in Cloudflare DNS → Records, then save the route. |

## Useful commands (via SSH)

```bash
# Container status
sudo docker ps

# App logs
sudo docker logs feed-platform-app --tail 100

# Last few pipeline runs
sudo docker exec feed-platform-app sqlite3 /app/data/niche.db \
  "SELECT started_at, status, items_fetched, items_in_digest FROM pipeline_runs ORDER BY started_at DESC LIMIT 5;"
```
