# Architectural Decisions

2026-04-28  Stack: Flask + SQLite + Jinja2 + vanilla JS. PythonAnywhere MVP; portable to Synology/Docker Compose. See SPEC.md §2.
2026-04-28  Scheduler: APScheduler embedded in WSGI process. PythonAnywhere always-on (Hacker plan) confirmed.
2026-04-28  Translation: DeepL primary (all non-English → English); Claude Haiku fallback. UI languages: English and German only.
2026-04-28  Clustering: rule-based (topic tag + company tag overlap) for v1. Semantic embeddings deferred.
2026-04-28  Digest personalization (M4 Q5): re-sort canonical top-30 using user weights; no per-user full re-rank in M4. One Digest row per run (user_id=null).
2026-04-28  Read-time floor (M4 Q7): min(1.0, word_count/200) — short regulatory items get 1-minute floor.
2026-04-28  Cluster label language (M4 Q8): English only. Single Sonnet call per run; bilingual labels deferred.
