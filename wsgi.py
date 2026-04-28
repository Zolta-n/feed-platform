from __future__ import annotations

import os

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

_resend_key = os.environ.get("RESEND_API_KEY")
if _resend_key:
    from niche.core.email.resend_provider import ResendProvider
    _email_provider = ResendProvider(_resend_key)
else:
    from niche.core.email.dev_provider import DevEmailProvider
    _email_provider = DevEmailProvider()

application = create_app({
    "REPO": _repo,
    "BUNDLE": _bundle,
    "APP_URL": os.environ.get("APP_URL", "http://localhost:5000"),
    "APPROVAL_SECRET": os.environ.get("APPROVAL_SECRET", "dev-approval-secret"),
    "EMAIL_PROVIDER": _email_provider,
})
