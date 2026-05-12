from __future__ import annotations

import json


def as_bullets(value) -> list[str] | None:
    """If `value` is a JSON-encoded list of non-empty strings, return the list.
    Otherwise return None so templates fall back to plain-text rendering.

    Used by digest and email templates to detect the executive-summary
    `key_points` format stored in Item.summary. Old items (plain prose)
    still parse as None and render unchanged.
    """
    if not value or not isinstance(value, str):
        return None
    try:
        parsed = json.loads(value)
    except (json.JSONDecodeError, ValueError):
        return None
    if not isinstance(parsed, list) or not parsed:
        return None
    if not all(isinstance(p, str) and p.strip() for p in parsed):
        return None
    return [p.strip() for p in parsed]
