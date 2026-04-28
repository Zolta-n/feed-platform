# Architectural Decisions

2026-04-28  Stack: Flask + SQLite + Jinja2 + vanilla JS. PythonAnywhere MVP; portable to Synology/Docker Compose. See SPEC.md §2.
2026-04-28  Scheduler: APScheduler embedded in WSGI process. PythonAnywhere always-on (Hacker plan) confirmed.
2026-04-28  Translation: DeepL primary (all non-English → English); Claude Haiku fallback. UI languages: English and German only.
2026-04-28  Clustering: rule-based (topic tag + company tag overlap) for v1. Semantic embeddings deferred.
