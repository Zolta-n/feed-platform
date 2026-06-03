# Synology NAS Deployment Guide

Runs the BrakeByWire feed at **https://bbw.businessintels.com** on a Synology DS225+
via Docker Compose + Cloudflare Tunnel.

## Prerequisites

| What | Status |
|---|---|
| Synology DS225+ with Container Manager installed | required |
| Cloudflare Tunnel `Synology-nas` running and HEALTHY | already done |
| SSH access to the NAS (`ssh admin@192.168.50.70`) | required |
| Git installed on the NAS | verify in step 1 |
| Anthropic API key | console.anthropic.com |
| Resend account + verified sender domain | resend.com |

---

## Step 1 — Verify Git on the NAS

SSH into the NAS:

```bash
ssh admin@192.168.50.70
```

Check git is available:

```bash
git --version
```

If not found, install it via Synology Package Center → search **Git Server** → install. Then re-SSH and confirm.

---

## Step 2 — Clone the repo

```bash
mkdir -p /volume1/docker/bbw
cd /volume1/docker/bbw
git clone https://github.com/Zolta-n/feed-platform.git .
```

The dot at the end clones into the current directory (not a sub-folder).

---

## Step 3 — Create the data directory

This is where SQLite will live. It is not in the repo (`.gitignore` excludes `.db` files).

```bash
mkdir -p /volume1/docker/bbw/data
```

---

## Step 4 — Generate secret strings

Run this command **twice** — once for `SESSION_SECRET`, once for `APPROVAL_SECRET`:

```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

Copy both outputs somewhere safe before moving to the next step.

---

## Step 5 — Create the `.env` file

```bash
nano /volume1/docker/bbw/.env
```

Paste and fill in all values:

```dotenv
# ── Required ──────────────────────────────────────────────────────
ANTHROPIC_API_KEY=sk-ant-...
SESSION_SECRET=<paste first token_hex output>
APPROVAL_SECRET=<paste second token_hex output>

# ── Email ─────────────────────────────────────────────────────────
RESEND_API_KEY=re_...

# ── Optional ──────────────────────────────────────────────────────
DEEPL_API_KEY=                    # leave blank → Haiku used for translation

# ── App config ────────────────────────────────────────────────────
APP_URL=https://bbw.businessintels.com
FEED_DIR=/app/feeds/brake-by-wire  # container-internal path — do not change
DB_PATH=/app/data/niche.db         # container-internal path — do not change
SCHEDULER_ENABLED=true             # enables APScheduler inside the container

# ── Cost caps ─────────────────────────────────────────────────────
DAILY_COST_CAP_USD=1.00
MONTHLY_COST_CAP_USD=18.00
```

Save: `Ctrl-O` → `Enter`. Exit: `Ctrl-X`.

> **`FEED_DIR` and `DB_PATH` use `/app/...` paths.** These are paths _inside_ the container.
> The `docker-compose.yml` mounts the NAS directories to those locations automatically.

---

## Step 6 — Set `from_email` in the feed config

Resend rejects mail from the placeholder address. Edit the feed config:

```bash
nano /volume1/docker/bbw/feeds/brake-by-wire/config.yaml
```

Change:
```yaml
from_email: "digest@yourdomain.com"
```
to your Resend-verified sender address, e.g.:
```yaml
from_email: "digest@businessintels.com"
```

Save and exit.

---

## Step 7 — Build and start the container

```bash
cd /volume1/docker/bbw
sudo docker-compose up -d --build
```

This pulls the Python base image, installs all dependencies, and starts the app.
First build takes 3–5 minutes depending on NAS speed.

Verify it is running:

```bash
sudo docker ps | grep bbw
```

You should see `bbw` with status `Up`.

Check the startup logs for errors:

```bash
sudo docker logs bbw --tail 50
```

A healthy start looks like:
```
[INFO] Starting gunicorn 21.2.0
[INFO] Listening at: http://0.0.0.0:8001
```

---

## Step 8 — Verify the app responds locally

On the NAS:

```bash
curl -s -o /dev/null -w "%{http_code}" http://192.168.50.70:8001/health
```

Should print `200`. If you see `000` or an error, check the logs in step 7.

---

## Step 9 — Add the Cloudflare route

1. Go to **one.dash.cloudflare.com** → **Networks** → **Connectors**
2. Click **Synology-nas**
3. Click **Published application routes** → **+ Add a published application route**
4. Fill in:

| Field | Value |
|---|---|
| Subdomain | `bbw` |
| Domain | `businessintels.com` |
| Path | *(leave empty)* |
| Type | HTTP |
| URL | `192.168.50.70:8001` |

5. Click **Save**

Cloudflare automatically creates the CNAME DNS record. It takes up to 60 seconds to propagate.

---

## Step 10 — Verify remote access

On your phone using **mobile data** (not WiFi), open:

```
https://bbw.businessintels.com
```

You should see the BrakeByWire login page with a valid HTTPS padlock. If it doesn't load yet, wait 60 seconds and try again.

---

## Step 11 — Promote yourself to admin

The database schema is created automatically on first startup. Now promote your account:

```bash
sudo docker exec -it bbw python cli.py admin promote --email your@email.com
```

Then open `https://bbw.businessintels.com/auth/request`, enter your email, and click the magic link in your inbox to log in.

---

## Step 12 — Run the pipeline for the first time

```bash
sudo docker exec -it bbw python cli.py pipeline run --feed-dir /app/feeds/brake-by-wire
```

Should complete and print a JSON summary with `"status": "complete"`.

Then visit `https://bbw.businessintels.com` — today's digest should appear.

---

## Step 13 — Verify the scheduler

APScheduler starts automatically with the container (`SCHEDULER_ENABLED=true`).
Confirm it registered the daily job:

```bash
sudo docker logs bbw | grep -i "scheduler\|APScheduler\|job"
```

You should see a line indicating the daily pipeline job was scheduled at the time configured in `feeds/brake-by-wire/config.yaml` (`daily_run_time`).

The pipeline also runs when you trigger it from the admin UI at
`https://bbw.businessintels.com/admin/`.

---

## Step 14 — Approve subscribers

New users self-register at `/auth/request`. You approve them at
`https://bbw.businessintels.com/admin/users`.

---

## Updating the app

When you push new code to `main`:

```bash
ssh admin@192.168.50.70
cd /volume1/docker/bbw
git pull origin main
sudo docker-compose up -d --build
```

The build reuses the pip layer cache if `requirements.txt` did not change — typically
fast (< 30 seconds). The database and `feeds/` are untouched by a rebuild.

---

## Editing prompts or feed config without rebuilding

Because `feeds/` is a mounted volume, you can edit any prompt or config file directly
on the NAS and restart the container without rebuilding the image:

```bash
nano /volume1/docker/bbw/feeds/brake-by-wire/prompts/summarize.md
sudo docker-compose restart
```

---

## Useful commands

```bash
# View live logs
sudo docker logs bbw -f

# Run a single agent for debugging
sudo docker exec -it bbw python cli.py agent fetch --feed-dir /app/feeds/brake-by-wire

# Open a shell inside the container
sudo docker exec -it bbw bash

# Restart without rebuilding
sudo docker-compose restart

# Stop the container
sudo docker-compose down

# Check SQLite directly
sudo docker exec -it bbw sqlite3 /app/data/niche.db \
  "SELECT started_at, status, items_fetched, items_in_digest FROM pipeline_runs ORDER BY started_at DESC LIMIT 5;"
```

---

## Troubleshooting

| Problem | Solution |
|---|---|
| `curl` returns `000` on port 8001 | Container not running — check `sudo docker ps` and `sudo docker logs bbw` |
| App loads locally but not at `bbw.businessintels.com` | Check Cloudflare tunnel shows HEALTHY and route URL is `192.168.50.70:8001` |
| `502 Bad Gateway` from Cloudflare | Container crashed — check `sudo docker logs bbw --tail 100` for traceback |
| Scheduler not firing | Confirm `SCHEDULER_ENABLED=true` in `.env` and check logs for APScheduler startup message |
| `FEED_DIR` or `DB_PATH` errors at startup | Paths in `.env` must be `/app/feeds/brake-by-wire` and `/app/data/niche.db` (container-internal) |
| Email not arriving | Confirm `from_email` in `config.yaml` matches a Resend-verified domain |
| NAS IP changed | Assign static IP to the NAS in your router's DHCP settings, then update the Cloudflare route URL |
