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

Watchtower (and the NAS `docker pull`) needs to fetch the image anonymously. The image is private
by default, so make its package public.

> **The package does not exist until Step 1's build succeeds.** Confirm the green tick in the
> **Actions** tab first — only then does the package appear under your account.

1. **Find the package.** Either:
   - Open `https://github.com/Zolta-n/feed-platform` → right sidebar → **Packages** → click
     **feed-platform**, **or**
   - Go directly to
     `https://github.com/users/Zolta-n/packages/container/feed-platform/settings`.
2. On the package page click **Package settings** (top-right gear, or the link in the sidebar).
3. Scroll to the bottom — **Danger Zone** → **Change visibility**.
4. Select **Public**, then type the package name `feed-platform` to confirm → **I understand,
   change package visibility**.
5. *(First build only)* Back on the package page, make sure it's **linked to the repository**:
   Package settings → **Manage Actions access** should already list `Zolta-n/feed-platform` with
   Write (the workflow's `GITHUB_TOKEN` does this automatically). No action needed if present.

**Verify it's public** from any machine *without* logging in to GHCR:

```bash
docker pull ghcr.io/zolta-n/feed-platform:latest    # succeeds if public
```

(or open the package page in a private/incognito browser window — a public package is viewable
logged-out.)

> **Prefer to keep it private?** Then skip this step and instead give the NAS a credential: create a
> GitHub **Personal Access Token (classic)** with `read:packages`, and on the NAS run
> `docker login ghcr.io -u Zolta-n -p <token>` once. Watchtower will reuse `~/.docker/config.json`.
> The public route is simpler and matches the reporting app — recommended.

### Step 3 — Create the NAS app folder + `.env`

You need a folder on the NAS holding `docker-compose.yml`, a `data/` subfolder for the database, and
a `.env` file with secrets. Do it via **File Station** (GUI) or **SSH** — both shown.

**3a. Create the folders.**

*File Station route:* DSM → **File Station** → open the existing **`docker`** shared folder (the
same one holding `reporting/` and `cloudflare/`) → **Create → Create folder** → `feed-platform`.
Open it → **Create folder** → `data`.

*SSH route:*
```bash
ssh admin@192.168.50.70
sudo mkdir -p /volume1/docker/feed-platform/data
```

**3b. Get `docker-compose.yml` onto the NAS.** Download it from the repo's `deploy` branch
(GitHub → file → **Raw → Save as**) and upload it into `/volume1/docker/feed-platform/` via File
Station. Or via SSH from a clone: `scp docker-compose.yml admin@192.168.50.70:/volume1/docker/feed-platform/`.

**3c. Generate the two secrets.** Each must be a long random string. On the NAS (`openssl` ships
with DSM):
```bash
openssl rand -hex 32     # run twice → one value for SESSION_SECRET, one for APPROVAL_SECRET
```
(Any machine works; or `python3 -c "import secrets; print(secrets.token_hex(32))"` if you have Python.)

**3d. Create `/volume1/docker/feed-platform/.env`** (DSM **Text Editor** package, or `vi` over SSH).
This file lives **only on the NAS** — never commit it. Contents:

```dotenv
# ── Secrets ──────────────────────────────────────────────
ANTHROPIC_API_KEY=sk-ant-...        # from console.anthropic.com
SESSION_SECRET=<first openssl rand -hex 32 value>
APPROVAL_SECRET=<second openssl rand -hex 32 value>
RESEND_API_KEY=re_...               # from resend.com; leave BLANK for dev (magic links shown in logs)
DEEPL_API_KEY=                      # optional; blank → Haiku fallback for translation

# ── Config ───────────────────────────────────────────────
APP_URL=https://bbw.businessintels.com
FEED_DIR=/app/feeds/brake-by-wire
DB_PATH=/app/data/niche.db
NICHE_DB_PATH=/app/data/niche.db
SCHEDULER_ENABLED=false
```

> **Why both `DB_PATH` and `NICHE_DB_PATH`?** `wsgi.py` reads `DB_PATH`; the CLI reads
> `NICHE_DB_PATH` (else defaults to an ephemeral in-container `niche.db`). Setting both points the
> web app *and* every CLI/scheduled run at the same persisted DB on the mounted volume.

**3e. Lock down the file** so secrets aren't world-readable (SSH):
```bash
sudo chmod 600 /volume1/docker/feed-platform/.env
```

**3f. Sender address — usually nothing to do.** `from_email` is already
`digest@businessintels.com` in `feeds/brake-by-wire/config.yaml`. As long as **businessintels.com is
verified in Resend** (it is for the reporting app), digests send fine. This value is **baked into
the image**, not read from `.env`, so to change it you edit `config.yaml` in the repo on the
`deploy` branch and push (CI rebuilds) — it cannot be changed on the NAS.

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
