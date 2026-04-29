# PythonAnywhere WSGI configuration
#
# Paste this file's contents into the WSGI configuration file in the
# PythonAnywhere Web tab (it lives at /var/www/<username>_pythonanywhere_com_wsgi.py).
# Adjust the paths and environment variables for your account.

import sys
import os

# ── 1. Add your project to the Python path ────────────────────────────────────
PROJECT_HOME = "/home/<username>/feed-platform"
if PROJECT_HOME not in sys.path:
    sys.path.insert(0, PROJECT_HOME)

# ── 2. Set environment variables (or use a .env file) ─────────────────────────
os.environ.setdefault("ANTHROPIC_API_KEY",  "sk-ant-...")
os.environ.setdefault("RESEND_API_KEY",     "re_...")
os.environ.setdefault("DEEPL_API_KEY",      "")
os.environ.setdefault("SESSION_SECRET",     "replace-with-long-random-string")
os.environ.setdefault("APPROVAL_SECRET",    "replace-with-long-random-string")
os.environ.setdefault("APP_URL",            "https://<username>.pythonanywhere.com")
os.environ.setdefault("FEED_DIR",           f"{PROJECT_HOME}/feeds/brake-by-wire")
os.environ.setdefault("DB_PATH",            f"{PROJECT_HOME}/niche.db")
os.environ.setdefault("SCHEDULER_ENABLED",  "true")

# ── 3. Import the WSGI application ────────────────────────────────────────────
from wsgi import application  # noqa: E402  (must be after sys.path setup)
