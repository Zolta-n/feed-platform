from __future__ import annotations

import os

from flask import Flask, jsonify


def create_app(config: dict | None = None) -> Flask:
    app = Flask(__name__)

    app.secret_key = os.environ.get("SESSION_SECRET", "dev-secret-change-in-production")

    if config:
        app.config.update(config)

    @app.route("/health")
    def health():
        return jsonify({"status": "ok"})

    return app
