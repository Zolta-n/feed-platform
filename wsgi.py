from __future__ import annotations

import os
import sys

from dotenv import load_dotenv

load_dotenv()

from niche.core.bundle_loader import load_bundle
from niche.core.models.repository import Repository
from niche.web.app import create_app

_feed_dir = os.environ["FEED_DIR"]
_db_path = os.environ.get("DB_PATH", "niche.db")

_bundle = load_bundle(_feed_dir)
_repo = Repository(_db_path)
_repo.create_schema()
_repo.seed_watchlist_from_bundle(_bundle.config.feed_id, _bundle.companies)

_resend_key = os.environ.get("RESEND_API_KEY")
if _resend_key:
    from niche.core.email.resend_provider import ResendProvider
    _email_provider = ResendProvider(_resend_key)
else:
    _email_provider = None

application = create_app({
    "REPO": _repo,
    "DB_PATH": _db_path,
    "FEED_DIR": _feed_dir,
    "PYTHON_EXECUTABLE": os.path.join(sys.prefix, "bin", "python3"),
    "BUNDLE": _bundle,
    "APP_URL": os.environ.get("APP_URL", "http://localhost:5000"),
    "APPROVAL_SECRET": os.environ.get("APPROVAL_SECRET", "dev-approval-secret"),
    "EMAIL_PROVIDER": _email_provider,
})
