# PythonAnywhere Deployment Guide

## Prerequisites

| What | Where |
|------|-------|
| PythonAnywhere **Hacker** plan | pythonanywhere.com — required for always-on scheduler |
| Anthropic API key | console.anthropic.com |
| Resend account + verified sender domain | resend.com |
| GitHub access to `Zolta-n/feed-platform` | already set up |

---

## Step 1 — Open a Bash console on PythonAnywhere

Dashboard → **Consoles** → **Bash**

---

## Step 2 — Clone the repo

```bash
git clone https://github.com/Zolta-n/feed-platform.git ~/feed-platform
cd ~/feed-platform
```

---

## Step 3 — Create a virtualenv (Python 3.12)

PythonAnywhere supports up to Python 3.12. Use that.

```bash
mkvirtualenv --python=/usr/bin/python3.12 feed-platform
# virtualenv activates automatically — prompt shows (feed-platform)
```

---

## Step 4 — Install dependencies

```bash
pip install -r requirements.txt
```

---

## Step 5 — Edit `from_email` in the feed config

Resend will reject emails from the placeholder address. Set it to your verified sender.

```bash
nano ~/feed-platform/feeds/brake-by-wire/config.yaml
```

Change:
```yaml
from_email: "digest@yourdomain.com"
```
to your Resend-verified sender address:
```yaml
from_email: "digest@your-verified-domain.com"
```
Save: `Ctrl-O` → `Enter`. Exit: `Ctrl-X`.

---

## Step 6 — Create the Web app

1. PA Dashboard → **Web** → **Add a new web app**
2. Choose **Manual configuration** (not the Flask wizard)
3. Select **Python 3.12**

---

## Step 7 — Configure the WSGI file

PA Web tab → click the WSGI configuration file link
(path looks like `/var/www/<username>_pythonanywhere_com_wsgi.py`).

**Replace the entire contents** with the template already in the repo at
`~/feed-platform/pythonanywhere_wsgi.py`, filling in real values:

```python
import sys, os

PROJECT_HOME = "/home/<username>/feed-platform"
if PROJECT_HOME not in sys.path:
    sys.path.insert(0, PROJECT_HOME)

os.environ.setdefault("ANTHROPIC_API_KEY",  "sk-ant-...")
os.environ.setdefault("RESEND_API_KEY",     "re_...")
os.environ.setdefault("DEEPL_API_KEY",      "")          # blank → uses Haiku for translation
os.environ.setdefault("SESSION_SECRET",     "<long-random-string>")
os.environ.setdefault("APPROVAL_SECRET",    "<long-random-string>")
os.environ.setdefault("APP_URL",            "https://<username>.pythonanywhere.com")
os.environ.setdefault("FEED_DIR",           f"{PROJECT_HOME}/feeds/brake-by-wire")
os.environ.setdefault("DB_PATH",            f"{PROJECT_HOME}/niche.db")
os.environ.setdefault("SCHEDULER_ENABLED",  "false")   # PA disables uWSGI threads — use PA Scheduled Tasks (see Step 13)

from wsgi import application  # noqa: E402
```

Generate the two secret strings in the Bash console (run this twice):

```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

---

## Step 8 — Set virtualenv path in Web tab

PA Web tab → **Virtualenv** section → enter:
```
/home/<username>/.virtualenvs/feed-platform
```

---

## Step 9 — Set working directory in Web tab

PA Web tab → **Source code** / **Working directory** → enter:
```
/home/<username>/feed-platform
```

---

## Step 10 — Reload and verify

Click **Reload** in the Web tab.

Visit `https://<username>.pythonanywhere.com` — you should see the feed login page.

If it doesn't load: Web tab → **Log files → Error log** for the traceback.

---

## Step 11 — Promote yourself to admin

The database schema and watchlist seed happen automatically on the first request
(`wsgi.py` calls `create_schema()` and `seed_watchlist_from_bundle()` at import time).

Promote your account in the Bash console:

```bash
cd ~/feed-platform
workon feed-platform
python cli.py admin promote --email your@email.com
```

---

## Step 12 — Run the pipeline for the first time

```bash
python cli.py pipeline run --feed-dir feeds/brake-by-wire
```

Should complete and print a JSON summary with `"status": "complete"`.

---

## Step 13 — Configure the daily schedule (PA Scheduled Tasks)

PythonAnywhere's shared uWSGI runs without threads, so the in-process
APScheduler cannot start (`SCHEDULER_ENABLED` must stay `false`). Use
PA's own Scheduled Tasks feature instead — it's a host-native cron
runner included with the Hacker plan and above.

1. PA Dashboard → **Tasks** tab → **Create a new scheduled task**.
2. **Command**:
   ```bash
   cd /home/<username>/feed-platform && /home/<username>/.virtualenvs/feed-platform/bin/python cli.py pipeline run --feed-dir feeds/brake-by-wire >> /home/<username>/feed-platform/pipeline_cron.log 2>&1
   ```
3. **Hour / Minute**: enter in UTC (PA tasks run in UTC, not your bundle's timezone). `05:30 Europe/Berlin` = `03:30` UTC in summer, `04:30` UTC in winter. Pick a time that doesn't need DST adjustments and stick with it.
4. Click **Create**.

PA executes the command at the configured UTC time every day. Logs land in `pipeline_cron.log` for inspection.

To verify the task is registered:
```bash
ls -la ~/feed-platform/pipeline_cron.log    # appears after first run
sqlite3 ~/feed-platform/niche.db "SELECT started_at, status, items_fetched, items_in_digest FROM pipeline_runs ORDER BY started_at DESC LIMIT 5;"
```

The admin UI's **Schedule** panel sets a value in the DB (`scheduler_run_time` in `app_config`) which the in-process scheduler would honor — on PA it's informational only; the actual schedule is in PA's Tasks tab.

---

## Step 14 — Verify email delivery

Admin panel → **Send digest** → check your inbox.

If no email arrives: check the Resend dashboard and confirm `from_email` in
`config.yaml` matches a Resend-verified domain.

---

## Step 15 — Approve subscribers

New users self-register at `/auth/login`. You approve them at `/admin/users`.

---

## Updating the app

```bash
cd ~/feed-platform
workon feed-platform
git pull origin main
pip install -r requirements.txt   # in case dependencies changed
```

Then click **Reload** in the PA Web tab.
