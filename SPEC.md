# SPEC.md — Niche Feed Platform

```
Version:    0.1-draft
Date:       2026-04-28
Status:     Approved — implementation begins at M1
PRD anchor: PRD.md v0.2
```

---

## Table of Contents

1. [Overview](#1-overview)
2. [Stack Decision](#2-stack-decision)
3. [Directory Structure](#3-directory-structure)
4. [Data Model](#4-data-model)
5. [Feed Bundle Loader](#5-feed-bundle-loader)
6. [Source Adapter Interface](#6-source-adapter-interface)
7. [Pipeline Architecture](#7-pipeline-architecture)
8. [Agent Specifications](#8-agent-specifications)
9. [Scheduling](#9-scheduling)
10. [Auth Flow](#10-auth-flow)
11. [Web UI](#11-web-ui)
12. [Email Subsystem](#12-email-subsystem)
13. [Cost Tracking and Budget Enforcement](#13-cost-tracking-and-budget-enforcement)
14. [Admin Dashboard](#14-admin-dashboard)
15. [GDPR Compliance](#15-gdpr-compliance)
16. [Build Plan — Milestones](#16-build-plan--milestones)
17. [Risks and Mitigations](#17-risks-and-mitigations)
18. [Open Questions](#18-open-questions)

---

## 1. Overview

**Platform name:** Niche — used in code namespaces (`niche/`), Docker image names, admin dashboard header. Not user-facing on the web.

**First feed:** BrakeByWire — brand rendered entirely from `feeds/brake-by-wire/config.yaml`. No module inside `niche/core/` is aware of the brake-by-wire domain.

**Hosting target:** PythonAnywhere for MVP (Python-only, WSGI, no Docker). Architecture kept portable for later migration to Synology NAS running Docker Compose. No PythonAnywhere-specific API calls anywhere in `niche/core/` or `niche/web/`.

**Budget:** $20/month hard ceiling including hosting. LLM spend estimated at ~$2.70/month under normal load. See §8 and §13.

**Single-feed v1:** One active feed per deployment. Multi-feed runtime is a v2 concern. The schema and `feed_id` convention do not block it.

**EP rule index:** EP1–EP10 are defined in CLAUDE.md and PRD §7.2. This document references them by number only.

---

## 2. Stack Decision

### 2.1 Framework: Flask

| Criterion | Flask | FastAPI | Django |
|---|---|---|---|
| PythonAnywhere WSGI fit | Excellent — standard `application = create_app()` WSGI object | Requires ASGI worker; PythonAnywhere does not support ASGI natively | Excellent WSGI fit but ORM and admin stack conflict with EP6 Storage interface |
| Server-rendered editorial UI | Jinja2 built-in; no extra dependency | Templates possible but not idiomatic; ecosystem is JSON-API-first | Excellent templates but full framework is overkill |
| EP rule compatibility | Minimal surface area; EP6 interface pattern easy to maintain | Would work but async adds complexity for synchronous pipeline stages | Django ORM would fight EP5/EP6 conventions |
| Docker portability later | `Dockerfile` with gunicorn + Flask is one-liner | Minor ASGI/worker config change needed | Works but carries Django-specific Docker steps |
| Dependency weight | ~7 MB | ~15 MB | ~40 MB |

**Decision: Flask.** The pipeline is CPU/IO-bound batch work running once per day, not high-concurrency async. Synchronous is simpler and PythonAnywhere-native.

### 2.2 Supporting Libraries

| Library | Role | Notes |
|---|---|---|
| `flask` | Web framework + WSGI app | v3.x |
| `flask-login` | Session and user management | |
| `flask-wtf` | CSRF protection on forms | |
| `jinja2` | HTML templates (bundled with Flask) | |
| `feedparser` | RSS/Atom parsing | All RSS sources go through this |
| `httpx` | HTTP client (sync mode) | GDELT, scraping, DeepL, health checks |
| `beautifulsoup4` + `lxml` | HTML scraping for press rooms | |
| `apscheduler` | Embedded in-process scheduler | See §9 |
| `deepl` | Official DeepL Python SDK | Primary translator |
| `anthropic` | Anthropic Python SDK | Haiku default; Sonnet for clustering/lead |
| `pyyaml` | Feed bundle config loading | |
| `sqlite3` | Standard library — no ORM in v1 | Raw SQL behind Repository interface (EP6) |
| `resend` | Email delivery SDK | Magic-link + digest emails |
| `python-dotenv` | `.env` loading in development | |
| `click` | CLI entry points for every agent | |
| `pytest` | Test runner | |
| `pytest-flask` | Flask test client integration | |

**Explicitly excluded:**
- SQLAlchemy — adds migration complexity not needed for SQLite v1; swappable via EP6 Storage interface when Postgres is needed
- Any Node.js toolchain — PythonAnywhere constraint; no npm, no Webpack, no Vite
- Redis / Celery — overkill for one pipeline run per day; APScheduler with SQLite job store is sufficient

### 2.3 Front-End Approach

**Server-rendered Jinja2 + vanilla JS + plain CSS.** No build step. Rationale:

- PythonAnywhere provides no Node.js environment and no persistent build step.
- The UI is primarily a read-heavy editorial feed. All interactivity (thumbs, filter tabs, mark-as-read) is achievable with `fetch()` calls to Flask JSON endpoints and minimal DOM manipulation.
- EP7 (feed theme via props) is implemented via Jinja2 context variables and CSS custom properties injected from `config.yaml` into `<head>` — no component framework needed.
- Dark editorial aesthetic (PRD Appendix A) is straightforward with a single dark-theme stylesheet and CSS custom properties for the accent color.

CSS architecture: `static/css/niche.css` for platform base styles. Feed accent color and font overrides injected as a `<style>` block in `base.html` rendered from `FeedBundle.config`.

---

## 3. Directory Structure

```
/workspaces/feed-platform/
├── niche/                              # Main Python package
│   ├── __init__.py
│   ├── core/
│   │   ├── __init__.py
│   │   ├── bundle_loader.py            # FeedBundle loader + validator
│   │   ├── sources/
│   │   │   ├── __init__.py
│   │   │   ├── base.py                 # Source Protocol + RawItem dataclass
│   │   │   ├── rss.py                  # RSS/Atom adapter (feedparser)
│   │   │   ├── gdelt.py                # GDELT v2 API adapter
│   │   │   ├── google_news.py          # Google News RSS adapter
│   │   │   ├── scraper.py              # Generic HTML press-room scraper
│   │   │   ├── regulatory.py           # Regulatory feed adapter
│   │   │   └── factory.py              # source_type → adapter class registry
│   │   ├── pipeline/
│   │   │   ├── __init__.py
│   │   │   ├── runner.py               # Stage orchestrator; threads run_id
│   │   │   ├── dedup.py                # Pure function: deduplication stage
│   │   │   ├── classify.py             # Pure function: topic/type/region/company
│   │   │   ├── translate.py            # Pure function: translation stage
│   │   │   ├── summarize.py            # Pure function: summarization stage
│   │   │   ├── rank.py                 # Pure function: ranking stage
│   │   │   ├── cluster.py              # Pure function: clustering stage
│   │   │   └── compose.py              # Pure function: digest composition stage
│   │   ├── agents/
│   │   │   ├── __init__.py
│   │   │   ├── fetcher.py              # Fetcher agent + CLI entry point
│   │   │   ├── deduper.py              # Deduper agent + CLI entry point
│   │   │   ├── classifier.py           # Classifier agent + CLI entry point
│   │   │   ├── translator.py           # Translator agent + CLI entry point
│   │   │   ├── summarizer.py           # Summarizer agent + CLI entry point
│   │   │   ├── ranker.py               # Ranker agent + CLI entry point
│   │   │   ├── clusterer.py            # Clusterer agent + CLI entry point
│   │   │   ├── composer.py             # Digest Composer agent + CLI entry point
│   │   │   └── sender.py               # Email Sender agent + CLI entry point
│   │   ├── models/
│   │   │   ├── __init__.py
│   │   │   ├── schema.py               # CREATE TABLE statements
│   │   │   ├── repository.py           # Storage interface (EP6) + SQLite impl
│   │   │   └── types.py                # Dataclasses: RawItem, Item, Digest, User, …
│   │   ├── ranker/
│   │   │   ├── __init__.py
│   │   │   └── formula.py              # score = source_weight × topic_weight × …
│   │   ├── clusterer/
│   │   │   ├── __init__.py
│   │   │   └── rule_based.py           # Tag-overlap clustering
│   │   ├── translator/
│   │   │   ├── __init__.py
│   │   │   ├── base.py                 # Translator ABC (EP6)
│   │   │   ├── deepl_translator.py     # DeepL implementation
│   │   │   └── haiku_translator.py     # Haiku fallback implementation
│   │   ├── summarizer/
│   │   │   ├── __init__.py
│   │   │   └── haiku_summarizer.py     # Summary + why-it-matters via Haiku
│   │   ├── email/
│   │   │   ├── __init__.py
│   │   │   ├── base.py                 # EmailProvider ABC (EP6)
│   │   │   └── resend_provider.py      # Resend implementation
│   │   ├── auth/
│   │   │   ├── __init__.py
│   │   │   └── magic_link.py           # Token generation, validation, expiry
│   │   ├── scheduler/
│   │   │   ├── __init__.py
│   │   │   └── apscheduler_impl.py     # APScheduler embedded scheduler
│   │   └── cost/
│   │       ├── __init__.py
│   │       ├── tracker.py              # Per-call logging + daily cap enforcement
│   │       └── pricing.py              # Static Anthropic token price table
│   └── web/
│       ├── __init__.py
│       ├── app.py                      # Flask app factory: create_app(config)
│       ├── blueprints/
│       │   ├── __init__.py
│       │   ├── digest.py               # / and /digest/<date>
│       │   ├── auth.py                 # /auth/request, /auth/verify, /auth/logout
│       │   ├── preferences.py          # /preferences
│       │   ├── archive.py              # /archive
│       │   ├── api.py                  # /api/v1/… (thumbs, read signals, filters)
│       │   └── admin.py                # /admin/…
│       ├── templates/
│       │   ├── base.html               # Dark editorial layout; theme vars injected
│       │   ├── digest/
│       │   │   ├── index.html
│       │   │   └── item_detail.html
│       │   ├── auth/
│       │   │   ├── request_access.html
│       │   │   └── magic_link_sent.html
│       │   ├── preferences/
│       │   │   └── index.html
│       │   ├── archive/
│       │   │   └── index.html
│       │   ├── admin/
│       │   │   ├── dashboard.html
│       │   │   ├── sources.html
│       │   │   ├── users.html
│       │   │   └── costs.html
│       │   └── email/
│       │       └── digest.html         # Email template — inline CSS only
│       └── static/
│           ├── css/
│           │   └── niche.css           # Platform base styles (dark editorial)
│           └── js/
│               └── niche.js            # Vanilla JS: thumbs, filters, mark-as-read
├── feeds/
│   ├── brake-by-wire/
│   │   ├── config.yaml
│   │   ├── sources.yaml
│   │   ├── taxonomy.yaml
│   │   ├── watchlist.yaml
│   │   └── prompts/
│   │       ├── summarize.md
│   │       ├── classify-topic.md
│   │       ├── classify-item-type.md
│   │       ├── why-it-matters.md
│   │       └── translate.md
│   └── test-fixture/
│       ├── config.yaml
│       ├── sources.yaml
│       ├── taxonomy.yaml
│       ├── watchlist.yaml
│       └── prompts/
│           ├── summarize.md
│           ├── classify-topic.md
│           ├── classify-item-type.md
│           ├── why-it-matters.md
│           └── translate.md
├── tests/
│   ├── conftest.py                     # Loads test-fixture feed; never brake-by-wire
│   ├── fixtures/                       # Local RSS/HTML files for source adapter tests
│   ├── unit/
│   │   ├── test_dedup.py
│   │   ├── test_classify.py
│   │   ├── test_ranker.py
│   │   ├── test_clusterer.py
│   │   ├── test_composer.py
│   │   └── test_cost_tracker.py
│   └── integration/
│       ├── test_pipeline_end_to_end.py
│       ├── test_source_adapters.py
│       └── test_feed_bundle_loader.py
├── cli.py                              # Main CLI entry point (click group)
├── wsgi.py                             # PythonAnywhere WSGI entry point
├── requirements.txt
├── .env.example
├── .gitignore
├── CLAUDE.md
├── PRD.md
├── SPEC.md                             # This file
├── DECISIONS.md
└── NOTES.md
```

### EP1 CI Enforcement

A test in `tests/integration/test_pipeline_end_to_end.py` runs a `grep` against every `.py` file under `niche/core/` and `niche/web/` checking for a deny list of known domain strings. The deny list path is passed as a parameter — it is never hardcoded in the test itself. The deny list lives at `feeds/brake-by-wire/ci_deny_list.txt`. If any match is found, the test fails with the file path and line number. This makes EP1 machine-enforceable.

---

## 4. Data Model

**Storage:** SQLite (`niche.db`) for PythonAnywhere MVP. All DB access goes through the `Repository` interface in `niche/core/models/repository.py` (EP6), so upgrading to PostgreSQL is a single-file swap.

**Invariant:** Every table carries `feed_id` (EP5). `feed_id` is the slug from `config.yaml` (e.g. `"brake-by-wire"`). Schema is unchanged when a second feed is added to the same deployment.

**SQLite settings applied at startup:** `PRAGMA journal_mode=WAL;` `PRAGMA foreign_keys=ON;`

### `items` — canonical processed item

| Column | Type | Notes |
|---|---|---|
| `id` | TEXT PK | UUID4 |
| `feed_id` | TEXT NOT NULL | EP5 |
| `url` | TEXT NOT NULL | canonical URL |
| `url_hash` | TEXT | SHA-256 of normalized URL |
| `title` | TEXT | original language |
| `title_translated` | TEXT | null if source = target language |
| `body_raw` | TEXT | original-language excerpt; truncated to 1,000 chars at fetch |
| `body_translated` | TEXT | null if not translated |
| `summary` | TEXT | 2–3 sentence Haiku summary |
| `why_it_matters` | TEXT | one-line Haiku blurb |
| `source_id` | TEXT FK → sources.id | |
| `source_name` | TEXT | denormalized for display |
| `source_language` | TEXT | ISO 639-1 |
| `topic_tag` | TEXT | enum from taxonomy; null if classification failed |
| `item_type` | TEXT | breaking / analysis / report / exclusive |
| `region_tag` | TEXT | Americas / Europe / Asia |
| `company_tags` | TEXT | JSON array of watchlist slugs |
| `translation_failed` | INTEGER | 0/1 |
| `translation_provider` | TEXT | "deepl" / "haiku" / null |
| `relevance_score` | REAL | computed by ranker for default preferences |
| `published_at` | TEXT | ISO-8601 |
| `fetched_at` | TEXT | ISO-8601 |
| `run_id` | TEXT FK → pipeline_runs.id | |
| `word_count` | INTEGER | |
| `read_time_min` | REAL | word_count / 200 |
| `is_duplicate` | INTEGER | 0/1 |
| `duplicate_of` | TEXT | FK → items.id; null if not duplicate |

### `sources` — registered source instances

| Column | Type | Notes |
|---|---|---|
| `id` | TEXT PK | slug, e.g. "bosch-press-rss" |
| `feed_id` | TEXT NOT NULL | EP5 |
| `source_type` | TEXT | rss / gdelt / google_news / scraper / regulatory |
| `url` | TEXT | |
| `name` | TEXT | display name |
| `default_region` | TEXT | |
| `default_topic` | TEXT | |
| `source_weight` | REAL | default 1.0; used in ranker formula |
| `enabled` | INTEGER | 0/1 |
| `last_fetch_at` | TEXT | ISO-8601 |
| `last_fetch_status` | TEXT | ok / empty / error |
| `consecutive_failures` | INTEGER | |
| `added_by` | TEXT | "config" or user_id |

### `users`

| Column | Type | Notes |
|---|---|---|
| `id` | TEXT PK | UUID4 |
| `feed_id` | TEXT NOT NULL | EP5 |
| `email` | TEXT UNIQUE NOT NULL | |
| `is_admin` | INTEGER | 0/1 |
| `is_approved` | INTEGER | 0/1 |
| `ui_language` | TEXT | "en" / "de" |
| `created_at` | TEXT | ISO-8601 |
| `last_seen_at` | TEXT | ISO-8601 |
| `email_enabled` | INTEGER | 0/1; default 1 |
| `email_send_time` | TEXT | "06:30" in user's local time |
| `email_item_count` | INTEGER | default 15 |
| `deleted_at` | TEXT | soft-delete; null = active |

### `preferences` — per-user weights

| Column | Type | Notes |
|---|---|---|
| `id` | TEXT PK | UUID4 |
| `user_id` | TEXT FK → users.id | |
| `feed_id` | TEXT NOT NULL | EP5 |
| `region_weights` | TEXT | JSON: `{"americas": 1.0, "europe": 1.2, "asia": 0.8}` |
| `topic_weights` | TEXT | JSON: `{"tier1": 1.5, "oem": 1.0, "regulation": 1.0, "technology": 1.0}` |
| `company_boosts` | TEXT | JSON: `{"company-slug": 2.0, …}` |
| `keyword_boosts` | TEXT | JSON array of `{term, weight}` |
| `keyword_blocks` | TEXT | JSON array of terms |
| `updated_at` | TEXT | ISO-8601 |

### `digests` — one canonical record per day; one per user if re-scored

| Column | Type | Notes |
|---|---|---|
| `id` | TEXT PK | UUID4 |
| `feed_id` | TEXT NOT NULL | EP5 |
| `user_id` | TEXT FK → users.id | null = canonical (default preferences) |
| `run_id` | TEXT FK → pipeline_runs.id | |
| `date` | TEXT | YYYY-MM-DD |
| `item_ids` | TEXT | JSON array of item IDs in display order |
| `cluster_map` | TEXT | JSON: `[{label, item_ids, display_order}]` |
| `total_read_time_min` | REAL | |
| `item_count` | INTEGER | |
| `created_at` | TEXT | ISO-8601 |
| `email_sent_at` | TEXT | null if not yet sent |

### `feedback` — thumbs signals

| Column | Type | Notes |
|---|---|---|
| `id` | TEXT PK | UUID4 |
| `feed_id` | TEXT NOT NULL | EP5 |
| `user_id` | TEXT FK → users.id | anonymized (set to null) after account deletion |
| `item_id` | TEXT FK → items.id | |
| `signal` | TEXT | "up" / "down" |
| `created_at` | TEXT | ISO-8601 |

### `read_log`

| Column | Type | Notes |
|---|---|---|
| `id` | TEXT PK | UUID4 |
| `feed_id` | TEXT NOT NULL | EP5 |
| `user_id` | TEXT FK → users.id | |
| `item_id` | TEXT FK → items.id | |
| `source` | TEXT | "web" / "email" |
| `read_at` | TEXT | ISO-8601 |
| `pruned` | INTEGER | 0/1; rows marked pruned at 180 days |

### `llm_cost_log` — every LLM API call

| Column | Type | Notes |
|---|---|---|
| `id` | TEXT PK | UUID4 |
| `feed_id` | TEXT NOT NULL | EP5 |
| `run_id` | TEXT | |
| `agent` | TEXT | "summarizer" / "classifier" / "clusterer" / "translator" |
| `model` | TEXT | "claude-haiku-4-5" / "claude-sonnet-4-6" |
| `prompt_name` | TEXT | from prompt file front-matter |
| `prompt_version` | INTEGER | from prompt file front-matter |
| `input_tokens` | INTEGER | |
| `output_tokens` | INTEGER | |
| `cache_read_tokens` | INTEGER | |
| `cache_write_tokens` | INTEGER | |
| `usd` | REAL | computed from pricing.py |
| `called_at` | TEXT | ISO-8601 |

### `pipeline_runs`

| Column | Type | Notes |
|---|---|---|
| `id` | TEXT PK | UUID4 — the `run_id` threaded through all logs |
| `feed_id` | TEXT NOT NULL | EP5 |
| `started_at` | TEXT | ISO-8601 |
| `finished_at` | TEXT | ISO-8601 |
| `status` | TEXT | running / complete / failed / aborted_cost |
| `items_fetched` | INTEGER | |
| `items_after_dedup` | INTEGER | |
| `items_in_digest` | INTEGER | |
| `total_usd` | REAL | |
| `error_message` | TEXT | |

### `magic_link_tokens`

| Column | Type | Notes |
|---|---|---|
| `token` | TEXT PK | `secrets.token_hex(32)` |
| `email` | TEXT NOT NULL | |
| `expires_at` | TEXT | ISO-8601; 15 minutes from creation |
| `used` | INTEGER | 0/1 |
| `created_at` | TEXT | ISO-8601 |

### `source_health` — updated after each run

| Column | Type | Notes |
|---|---|---|
| `source_id` | TEXT PK FK → sources.id | |
| `feed_id` | TEXT NOT NULL | EP5 |
| `last_ok_at` | TEXT | ISO-8601 |
| `last_error_at` | TEXT | ISO-8601 |
| `last_error_message` | TEXT | |
| `consecutive_failures` | INTEGER | |
| `is_flagged` | INTEGER | 1 if consecutive_failures ≥ 3 |

---

## 5. Feed Bundle Loader

The bundle loader lives at `niche/core/bundle_loader.py`. It is the single point where domain configuration enters the platform without violating EP1 — everything it returns is a typed Python object; no raw dicts leak into pipeline code.

### 5.1 Config file formats

**`config.yaml`**

```yaml
feed_id: brake-by-wire        # must match directory name
name: BrakeByWire
tagline: "Industry Intelligence"
accent_color: "#E63946"       # hex; applied as --accent CSS custom property
logo_path: null               # optional; relative to feeds/<id>/static/
ui_languages: ["en", "de"]
default_ui_language: en
timezone: Europe/Berlin
daily_run_time: "05:00"
from_email: "digest@yourdomain.com"
```

**`taxonomy.yaml`**

```yaml
topics:
  - id: tier1
    label: "Tier-1"
    weight: 1.0
  - id: oem
    label: "OEM"
    weight: 1.0
  - id: regulation
    label: "Regulation"
    weight: 1.0
  - id: technology
    label: "Technology"
    weight: 1.0
regions:
  - id: americas
    label: "Americas"
  - id: europe
    label: "Europe"
  - id: asia
    label: "Asia"
item_types:
  - id: breaking
    label: "Breaking"
    badge_color: "#F4A261"
  - id: analysis
    label: "Analysis"
    badge_color: "#4361EE"
  - id: report
    label: "Report"
    badge_color: "#E63946"
  - id: exclusive
    label: "Exclusive"
    badge_color: "#2DC653"
nav_tabs:
  - {id: all,        label: "ALL"}
  - {id: tier1,      label: "TIER-1"}
  - {id: oem,        label: "OEM"}
  - {id: technology, label: "TECHNOLOGY"}
  - {id: regulation, label: "REGULATION"}
```

**`sources.yaml`** (abbreviated)

```yaml
sources:
  - id: example-trade-press
    type: rss
    url: "https://example.com/feed.xml"
    name: "Example Trade Press"
    default_region: europe
    default_topic: tier1
    source_weight: 1.2
    enabled: true
  - id: gdelt-main
    type: gdelt
    name: "GDELT Global News"
    source_weight: 0.8
    enabled: true
  - id: example-pressroom
    type: scraper
    url: "https://pressroom.example.com/news"
    name: "Example Press Room"
    item_selector: "article.press-release"
    title_selector: "h2"
    link_selector: "a"
    date_selector: "time"
    default_region: europe
    default_topic: tier1
    source_weight: 1.5
    enabled: true
```

**`watchlist.yaml`** (abbreviated)

```yaml
companies:
  - id: acme-tier1
    name: "Acme Tier1 Co"
    value_chain_role: tier1
    relationships: [customer, competitor]
    aliases: ["Acme T1", "AcmeTier1"]
    boost: 2.0
```

**Prompt front-matter** (required in every `.md` file)

```markdown
---
name: summarize
version: 1
model: claude-haiku-4-5
last_updated: 2026-04-28
max_input_tokens: 800
---
[prompt body]
```

### 5.2 Loader behavior

1. Reads `NICHE_FEED_DIR` environment variable (e.g. `feeds/brake-by-wire`).
2. Parses all four YAML files with strict validation — missing required keys raise `BundleValidationError` with a clear message identifying the missing key.
3. Loads all `.md` files from `prompts/`; validates front-matter; indexes by `name`.
4. Returns a frozen `FeedBundle` dataclass. No raw dicts leave the loader.
5. At startup, syncs `sources` table rows from `sources.yaml` (insert-or-update; never auto-deletes enabled sources).

### 5.3 Bundle validator CLI

```bash
python cli.py bundle validate --feed-dir feeds/brake-by-wire
```

Checks:
- All required YAML keys present and correctly typed.
- `feed_id` matches the directory name.
- Each source `type` has a registered adapter in `SOURCE_REGISTRY`.
- All prompt names match those expected by the pipeline stages.
- EP1 grep check: no domain strings in `niche/core/` or `niche/web/`.

---

## 6. Source Adapter Interface

### 6.1 Base contract (EP2)

```python
# niche/core/sources/base.py

from dataclasses import dataclass, field
from typing import Protocol
import datetime

@dataclass
class RawItem:
    source_id: str
    url: str
    title: str
    body: str            # raw text or HTML excerpt; may be empty
    language: str        # ISO 639-1; "en" if unknown
    published_at: datetime.datetime | None
    fetched_at: datetime.datetime
    extra: dict = field(default_factory=dict)  # adapter-specific metadata

class Source(Protocol):
    source_id: str

    def fetch(self) -> list[RawItem]:
        """
        Pull items since the last successful fetch.
        Must not raise — return [] on any failure and log internally.
        Caller reads source_health for error details.
        """
        ...
```

`Source` is a `Protocol` (structural subtyping), not an ABC, so adapters are independently testable without importing the base module.

### 6.2 Adapters

**RSSSource** (`core/sources/rss.py`)
- Uses `feedparser`. Handles Atom and RSS 2.0.
- Respects `If-Modified-Since` / `ETag` headers to avoid redundant fetches.
- `language` inferred from `feed.feed.language` field; defaults to `"en"` if absent.
- `body` = `entry.summary` with HTML tags stripped.
- Failure mode: `feedparser.bozo` error or HTTP failure → log error, return `[]`, update `source_health`.

**GDELTSource** (`core/sources/gdelt.py`)
- Queries GDELT v2 Article Search API.
- Query terms loaded from `FeedBundle` taxonomy at runtime — never hardcoded (EP1).
- Returns up to 250 results per run; deduplication handles overlaps with other sources.
- `language` = `"en"` (GDELT English-language results).
- Failure mode: HTTP 4xx/5xx → log, return `[]`.

**GoogleNewsSource** (`core/sources/google_news.py`)
- Google News RSS endpoint with search query terms from `FeedBundle` taxonomy (EP1).
- Same `feedparser`-based parsing as RSSSource.
- One query per configured search term group per run; terms from taxonomy.

**ScraperSource** (`core/sources/scraper.py`)
- For press rooms without RSS or with broken RSS.
- Config fields (all in `sources.yaml`): `url`, `item_selector`, `title_selector`, `link_selector`, `date_selector`.
- Uses `httpx` + `BeautifulSoup`.
- Politeness: 2-second delay between page requests; `User-Agent` header set to a descriptive bot string.
- Failure modes: selector mismatch → log warning, return `[]`; HTTP failure → log error, return `[]`.

**RegulatorySource** (`core/sources/regulatory.py`)
- Thin subtype of ScraperSource or RSSSource depending on what each body publishes.
- Items get `default_topic = "regulation"` applied before pipeline classification.
- Config field `regulatory_body_code` is an opaque string from `sources.yaml`; never interpreted in `core/` (EP1).

### 6.3 Source factory

```python
# niche/core/sources/factory.py

SOURCE_REGISTRY: dict[str, type] = {
    "rss":          RSSSource,
    "gdelt":        GDELTSource,
    "google_news":  GoogleNewsSource,
    "scraper":      ScraperSource,
    "regulatory":   RegulatorySource,
}

def build_sources(sources_config: list[SourceConfig]) -> list[Source]:
    ...
```

Adding a new source type = one adapter class + one entry in `SOURCE_REGISTRY`.
Adding a new source instance = one line in `sources.yaml`.

---

## 7. Pipeline Architecture

### 7.1 Stage sequence

```
Fetch → Dedup → Classify → Translate → Summarize → Rank → Cluster → Compose
```

Each stage is a pure function: `stage(items, config) → items` (EP3). The runner in `core/pipeline/runner.py` threads `run_id` through every call and logs entry/exit item counts and latency for each stage.

### 7.2 Stage boundary contracts

| After stage | What is guaranteed |
|---|---|
| **Fetch** | `list[RawItem]` — no DB writes yet |
| **Dedup** | `list[Item]`; duplicates flagged `is_duplicate=True`; all items batch-inserted to `items` table; duplicates excluded from downstream stages |
| **Classify** | `item.topic_tag`, `.item_type`, `.region_tag`, `.company_tags` populated (or null on LLM failure); DB updated |
| **Translate** | `.body_translated`, `.title_translated`, `.translation_failed`, `.translation_provider` populated; DB updated |
| **Summarize** | `.summary`, `.why_it_matters`, `.word_count`, `.read_time_min` populated; items without a summary excluded from Rank onward |
| **Rank** | `.relevance_score` populated; list sorted descending |
| **Cluster** | `list[Cluster]` produced alongside item list; clusters stored only in `Digest.cluster_map` |
| **Compose** | `Digest` record(s) written to DB |

### 7.3 Retry policy

| Stage | Retry behavior |
|---|---|
| Fetch (per source) | 3 attempts, 5 s exponential backoff. On final failure: source marked unhealthy, `[]` returned. Pipeline continues with items from other sources. |
| Classify (LLM) | 2 retries on Anthropic 5xx/529. On permanent failure: item carries `topic_tag=null`; still ranked (zero topic weight) and included in digest. |
| Translate — DeepL | 2 retries on 5xx. On failure: falls back to Haiku translator. |
| Translate — Haiku fallback | 1 retry. On failure: item marked `translation_failed=True`; carried forward without translation. Never served as if translated. |
| Summarize (LLM) | 2 retries. On permanent failure: item excluded from digest (no summary = not renderable). |
| Email send | 2 retries via Resend. On failure: log, do not retry until next run. |
| Cost cap exceeded | Pipeline aborts at the next stage boundary. Compose runs on completed items. Admin alert sent. `pipeline_runs.status = "aborted_cost"`. |

### 7.4 Trigger modes

- **Scheduled:** APScheduler fires daily at `FeedBundle.config.daily_run_time`.
- **CLI manual:** `python cli.py pipeline run --feed-dir feeds/brake-by-wire`
- **Admin UI manual:** POST to `/admin/pipeline/run` (requires `is_admin=1`).
- **Single-agent debug:** `python cli.py agent <name> --feed-dir feeds/brake-by-wire --run-id <uuid>`

---

## 8. Agent Specifications

Each agent wraps one or more pipeline stages and has a standalone CLI entry point. The underlying stage function is pure and directly unit-testable without the agent wrapper.

### 8.1 Fetcher

| | |
|---|---|
| **Input** | `FeedBundle` (source configs), `run_id` |
| **Output** | `list[RawItem]` in memory; no DB write |
| **Model** | None (network I/O only) |
| **CLI** | `python cli.py agent fetch --feed-dir <dir>` |

Process: instantiate sources via factory; call `source.fetch()` for each enabled source sequentially; log per-source item count and latency; update `source_health` for each source.

Failure modes: individual source failure → logged, flagged, skipped; all sources fail → `pipeline_runs.status = "failed"`, admin alerted.

**Cost: $0.00/run**

---

### 8.2 Deduper

| | |
|---|---|
| **Input** | `list[RawItem]`; existing URL hashes from DB for this `feed_id` (past 7 days) |
| **Output** | `list[Item]` with `is_duplicate` flag set |
| **Model** | None (heuristic) |
| **CLI** | `python cli.py agent dedup --feed-dir <dir> --run-id <uuid>` |

Process:
1. Normalize URL (strip tracking params, lowercase, canonical scheme).
2. SHA-256 of normalized URL → `url_hash`. Check against `items` table.
3. For items with novel URL: SHA-256 of normalized title. Check for title collision.
4. For remaining: fuzzy title similarity via `difflib.SequenceMatcher` (threshold 0.85). Items above threshold flagged as duplicates of the highest-scored match.

Failure mode: DB read failure → log, treat all items as non-duplicates (conservative).

**Cost: $0.00/run**

---

### 8.3 Classifier

| | |
|---|---|
| **Input** | `list[Item]` (non-duplicates), `FeedBundle` (taxonomy + prompts) |
| **Output** | `list[Item]` with `topic_tag`, `item_type`, `region_tag`, `company_tags` |
| **Model** | Claude Haiku (`claude-haiku-4-5`) |
| **CLI** | `python cli.py agent classify --feed-dir <dir> --run-id <uuid>` |

Process:
1. Topic + item-type classification: single Haiku call per item using combined `classify-topic.md` + `classify-item-type.md` prompt.
2. Region classification: rule-based first (source `default_region` if set; keyword matching against region terms from taxonomy). LLM called only if rule-based result is ambiguous.
3. Company tagging: string matching of title + body against watchlist `name` and `aliases` fields. No LLM.

**Prompt caching strategy:**
- **Cached prefix:** full taxonomy (topics, regions, item-types as enums), watchlist company list, few-shot examples (3 per topic class). Written on the first item; read-cached on all subsequent items in the same run.
- **Uncached suffix:** item title + body excerpt (max 400 tokens).

Failure mode: invalid JSON response → retry once at `temperature=0`. On second failure: item tagged `topic_tag=null`, logged, continues.

**Cost estimate (50 items/run, Haiku pricing):**

| Component | Tokens | USD |
|---|---|---|
| Cache write (prefix, once) | ~1,500 | ~$0.0012 |
| Cache reads (49 items) | ~1,500 × 49 | ~$0.0006 |
| Uncached input per item | ~450 × 50 | ~$0.018 |
| Output per item | ~80 × 50 | ~$0.016 |
| **Total classify** | | **~$0.036/run** |

---

### 8.4 Translator

| | |
|---|---|
| **Input** | `list[Item]` where `source_language ≠ target_language` |
| **Output** | `list[Item]` with `body_translated`, `title_translated`, `translation_provider` set |
| **Model** | DeepL primary; Claude Haiku (`claude-haiku-4-5`) fallback |
| **CLI** | `python cli.py agent translate --feed-dir <dir> --run-id <uuid>` |

Process:
1. Items with `source_language == "en"`: skip.
2. Batch non-English items. DeepL SDK `translate_text()` with `target_lang="EN-US"`.
3. On DeepL failure (network, quota, API error): fall back to Haiku with `translate.md` prompt.
4. Mark `translation_provider` on each item.
5. DeepL character usage logged to `llm_cost_log` with `model="deepl"` for auditability.

Failure modes:
- DeepL quota exhausted mid-run: switch to Haiku for remainder of run; alert admin.
- Both fail: item marked `translation_failed=True`. UI shows "[Translation unavailable]" label. Never served as if translated.

**Cost estimate (15 non-English items at ~300 chars each = 4,500 chars/run):**
- DeepL free tier: 500,000 chars/month. At 4,500 chars/day × 30 = 135,000 chars/month — well within limit.
- Haiku fallback (if triggered): ~$0.004/run.

**Translation cost: ~$0.00/run (DeepL free tier)**

---

### 8.5 Summarizer

| | |
|---|---|
| **Input** | `list[Item]` (post-translate), `FeedBundle` (summarize + why-it-matters prompts) |
| **Output** | `list[Item]` with `summary`, `why_it_matters`, `word_count`, `read_time_min` |
| **Model** | Claude Haiku (`claude-haiku-4-5`) |
| **CLI** | `python cli.py agent summarize --feed-dir <dir> --run-id <uuid>` |

Process:
1. Single Haiku call per item combining `summarize.md` + `why-it-matters.md`.
2. Output parsed as JSON: `{"summary": "...", "why_it_matters": "..."}`. On parse failure: retry once.
3. `word_count` = `len(summary.split())`. `read_time_min = word_count / 200`.

**Prompt caching strategy:** style guide and output format instructions in cached prefix; item body in uncached suffix.

Failure mode: permanent LLM failure → item excluded from digest (not renderable without a summary).

**Cost estimate (50 items/run):**

| Component | Tokens | USD |
|---|---|---|
| Cache write (prefix, once) | ~800 | ~$0.0006 |
| Uncached input per item | ~500 × 50 | ~$0.020 |
| Output per item | ~120 × 50 | ~$0.024 |
| **Total summarize** | | **~$0.045/run** |

---

### 8.6 Ranker

| | |
|---|---|
| **Input** | `list[Item]` (post-summarize), user preferences from `preferences` table, `FeedBundle` taxonomy weights |
| **Output** | `list[Item]` sorted by `relevance_score` descending |
| **Model** | None (pure arithmetic, EP8) |
| **CLI** | `python cli.py agent rank --feed-dir <dir> --run-id <uuid>` |

**Formula:**

```
score = (source_weight × topic_weight × company_boost)
        + recency_decay
        + thumbs_signal
```

Where:
- `source_weight` — from `sources` table (configured in `sources.yaml`)
- `topic_weight` — `preferences.topic_weights[item.topic_tag]` × `taxonomy.topics[item.topic_tag].weight`
- `company_boost` — `max(preferences.company_boosts[c] for c in item.company_tags)` if any match, else `1.0`
- `recency_decay` — `1.0 / (1 + hours_since_published / 24)` — halves every 24 hours
- `thumbs_signal` — sum of signals from `feedback` table for items sharing `topic_tag` + overlapping `company_tags` in past 30 days. Each thumbs-up = +0.1; thumbs-down = −0.15. Capped at ±0.5.
- Keyword blocks: items matching a blocked keyword are excluded entirely.
- Keyword boosts: matching items get `score × boost_factor` applied after the main formula.

All weights come from taxonomy/preferences. No domain logic in `niche/core/ranker/formula.py` (EP8).

Failure mode: pure arithmetic; no external dependencies. Cannot fail.

**Cost: $0.00/run**

---

### 8.7 Clusterer

| | |
|---|---|
| **Input** | `list[Item]` (ranked), `FeedBundle` taxonomy |
| **Output** | `list[Cluster]` — each with label, ordered item IDs, display rank |
| **Model** | Claude Sonnet (`claude-sonnet-4-6`) for label generation and lead blurb only; clustering logic is rule-based |
| **CLI** | `python cli.py agent cluster --feed-dir <dir> --run-id <uuid>` |

Process:
1. Rule-based grouping: items share a cluster if they share the same `topic_tag` AND have at least one overlapping company tag. Items with no company tag cluster by `topic_tag` alone.
2. Minimum cluster size: 2 items. Singletons go into a catch-all cluster.
3. Target: 3–5 clusters. If rule-based produces more, smallest clusters are merged until target is reached.
4. One Sonnet call per run: given cluster groupings + top item summaries, generate a one-sentence thematic label for each cluster and a one-paragraph lead blurb for the highest-ranked cluster.
5. Clusters ordered by sum of `relevance_score` of member items.

Failure mode: Sonnet unavailable → use `topic_tag` labels directly as cluster names; no blurb. Logged; admin notified.

**Cost estimate (Sonnet, 1 call/run, ~1,500 input tokens, ~300 output tokens):**

| Component | Tokens | USD |
|---|---|---|
| Input | ~1,500 | ~$0.0045 |
| Output | ~300 | ~$0.0045 |
| **Total cluster** | | **~$0.009/run** |

---

### 8.8 Digest Composer

| | |
|---|---|
| **Input** | Ranked + clustered `list[Item]`, `list[Cluster]`, user preferences |
| **Output** | `Digest` record(s) written to DB |
| **Model** | None |
| **CLI** | `python cli.py agent compose --feed-dir <dir> --run-id <uuid>` |

Process:
1. Start with top-ranked items. Accumulate until `sum(read_time_min) ≥ 15` minutes or item count reaches 30. Floor: 10 items minimum.
2. Apply cluster distribution: at least 1 item from each non-empty cluster represented.
3. Write canonical `Digest` record (`user_id=null`).
4. For users whose preferences differ materially from defaults: re-run Ranker with their weights, re-compose. Write a per-user `Digest` record.

Failure mode: pure logic; no external dependencies. DB write failure → pipeline run marked failed.

**Cost: $0.00/run**

---

### 8.9 Email Sender

| | |
|---|---|
| **Input** | `Digest` record, users with `email_enabled=True` and `is_approved=True`, `FeedBundle` theme |
| **Output** | Email sent via Resend; `Digest.email_sent_at` updated |
| **Model** | Resend API |
| **CLI** | `python cli.py agent send --feed-dir <dir> --run-id <uuid>` |

Process:
1. Render `templates/email/digest.html` with Jinja2 (inline CSS for email client compatibility). Feed name, accent color, item list injected as template variables (EP7).
2. Subject: `[{YYYY-MM-DD}] {feed_name} Brief — {item_count} items`.
3. Send via Resend. One email per user.
4. Click-through links wrapped with read-signal endpoint `/api/v1/read?item_id=…&user_token=…`.

Failure mode: Resend failure → 2 retries; on permanent failure, log and skip for that run. `email_sent_at` remains null. User receives email on next run. Never double-sends.

**Cost: $0.00/run** (Resend free tier: 3,000 emails/month; 20 users × 30 days = 600/month)

---

### 8.10 Daily cost budget summary

| Stage | Cost/run (50 items, 20 users) |
|---|---|
| Fetcher | $0.000 |
| Deduper | $0.000 |
| Classifier | ~$0.036 |
| Translator | ~$0.001 |
| Summarizer | ~$0.045 |
| Ranker | $0.000 |
| Clusterer (Sonnet) | ~$0.009 |
| Digest Composer | $0.000 |
| Email Sender | $0.000 |
| **Daily total** | **~$0.091** |
| **Monthly total** | **~$2.73** |

Headroom under $20/month ceiling: ~$17.27 (hosting, Resend, domain).

---

## 9. Scheduling

### Decision: APScheduler embedded in WSGI process

**PythonAnywhere scheduled tasks** (alternative): isolated process invocations triggered by PA's cron. Simple and reliable for daily runs, but: not triggerable from the admin UI, no real-time job state visibility, and limited to PA-configured times.

**APScheduler embedded** (chosen): runs inside the Flask WSGI worker.

Rationale:
- Enables manual pipeline trigger from the admin UI (`scheduler.trigger_job()`).
- Job state visible in real time in the admin dashboard.
- APScheduler `SQLAlchemyJobStore` pointing at the same SQLite DB survives WSGI worker restarts (the job metadata persists).
- Misfire grace time set to 1 hour — if the PA worker was down at scheduled time, the run fires within 1 hour.

**PythonAnywhere caveat:** always-on WSGI processes require the PA Hacker plan (~$5/month). On the free tier, APScheduler only runs while the WSGI process is alive (web request handling). Fallback for free tier: a PA scheduled task calls `POST /admin/pipeline/run` via `curl` with an admin API token. The scheduler interface in `core/scheduler/apscheduler_impl.py` is isolated — no PA-specific calls anywhere in `core/`.

**Configuration:** scheduler reads `FeedBundle.config.daily_run_time` and `FeedBundle.config.timezone`. `NICHE_FEED_DIR` env var controls which feed is active.

---

## 10. Auth Flow

### 10.1 Magic-link sign-in

1. User visits `/auth/request` and submits email.
2. Server checks `users` table:
   - Email not found → create user with `is_approved=0`. Send "pending approval" message to user. Send approval-request email to all users where `is_admin=1`.
   - Email found, `is_approved=0` → send "still pending" message. No new token.
   - Email found, `is_approved=1` → generate magic link token.
3. Token: `secrets.token_hex(32)`, stored in `magic_link_tokens` with `expires_at = now + 15 minutes`, `used=0`.
4. Resend sends login email: "Your login link — click within 15 minutes." Link: `{APP_URL}/auth/verify?token={token}`.
5. User clicks → GET `/auth/verify?token=…`.
6. Server validates: token exists, `used=0`, `expires_at > now`. On success: mark `used=1`, create Flask-Login session, redirect to `/`.
7. On invalid/expired: redirect to `/auth/request` with error flash.

### 10.2 Admin approval flow

1. Admin receives email with one-click approval link: `/admin/users/approve?token={hmac_token}` (HMAC-SHA256-signed with `SESSION_SECRET`, 72-hour expiry).
2. On click: `users.is_approved=1`. Welcome email sent to new user with their magic link.
3. Admin can also approve/reject from `/admin/users` dashboard.

### 10.3 Admin CLI promotion

```bash
python cli.py admin promote --email user@example.com
```

Sets `users.is_admin=1`. Requires direct server access. This is the only path to the admin role — no web endpoint.

### 10.4 Session security

- `SESSION_SECRET` from `.env` — minimum 32 random bytes.
- Flask-Login: `remember=False` — session cookie only, not persistent.
- Cookie flags: `SECURE=True`, `HTTPONLY=True`, `SAMESITE=Lax`.
- HTTPS enforced at the web server level (PA provides HTTPS termination).

---

## 11. Web UI

### 11.1 Theme injection (EP7)

`base.html` renders a `<style>` block in `<head>` containing CSS custom properties derived from `FeedBundle.config`:

```html
<style>
  :root {
    --accent:     {{ theme.accent_color }};
    --feed-name:  "{{ theme.name }}";
  }
</style>
```

Feed name, tagline, and nav tab labels are injected as Jinja2 context variables from `FeedBundle`. No feed-specific strings appear in any template or CSS file.

### 11.2 Routes

| Route | Blueprint | Auth | Description |
|---|---|---|---|
| `/` | digest | required | Redirect to `/digest/<today>` |
| `/digest/<date>` | digest | required | Digest for a specific date |
| `/item/<id>` | digest | required | Item detail view |
| `/archive` | archive | required | Searchable archive |
| `/preferences` | preferences | required | User preference wizard |
| `/auth/request` | auth | none | Email submission + new-user registration |
| `/auth/verify` | auth | none | Magic link landing |
| `/auth/logout` | auth | required | Logout |
| `/admin/` | admin | is_admin | Dashboard + pipeline status |
| `/admin/sources` | admin | is_admin | Source health table |
| `/admin/users` | admin | is_admin | User list + approval queue |
| `/admin/costs` | admin | is_admin | LLM cost log |
| `/admin/pipeline/run` | admin | is_admin | Manual pipeline trigger (POST) |
| `/api/v1/feedback` | api | required | POST thumbs signal |
| `/api/v1/read` | api | user_token | Mark item read (email click-through) |
| `/api/v1/digest/filter` | api | required | GET filtered digest items |
| `/gdpr/export` | api | required | User data export (JSON) |
| `/gdpr/delete` | api | required | User self-deletion (POST) |
| `/health` | — | none | Uptime check; returns 200 OK |

### 11.3 Item card fields

Type badge (color from taxonomy) · category tag (monospaced uppercase) · title · source name + initials avatar · timestamp · estimated read time · region tag · company tags · 2-sentence summary · why-it-matters · thumbs up/down · read indicator.

### 11.4 Vanilla JS interactions

All interactivity via `fetch()` to `/api/v1/` endpoints. No full page reload for:
- Thumbs up/down (optimistic UI; reverts on server error)
- Mark as read (fires on item click)
- Filter tabs (shows/hides cards by `data-topic` attribute)
- Grid density toggle (adds/removes CSS class on grid container)

---

## 12. Email Subsystem

### 12.1 Provider: Resend (EP6)

`EmailProvider` ABC in `niche/core/email/base.py`. `ResendProvider` implementation in `resend_provider.py`. Swapping to Mailgun or SES is a one-file change.

`RESEND_API_KEY` from `.env`. `from_email` from `FeedBundle.config`. EU endpoint used where available (GDPR data residency preference).

### 12.2 Email template

`templates/email/digest.html`: Jinja2 with inline CSS (no external stylesheets — email client compatibility). Feed name, accent color, tagline, and item list injected as template variables (EP7). No hardcoded feed-specific content in the template.

### 12.3 Unsubscribe

Each email includes a one-click unsubscribe link: `/auth/unsubscribe?token={hmac_token}` (HMAC-SHA256-signed, permanent validity). Sets `users.email_enabled=0`. List-Unsubscribe header included. CAN-SPAM and GDPR compliant.

---

## 13. Cost Tracking and Budget Enforcement

### 13.1 Per-call logging

Every LLM call (Anthropic and DeepL) passes through `niche/core/cost/tracker.py`:

1. Accepts: `run_id`, `agent`, `model`, `prompt_name`, `prompt_version`, `input_tokens`, `output_tokens`, `cache_read_tokens`, `cache_write_tokens`.
2. Computes `usd` from the static price table in `cost/pricing.py` (updated when Anthropic adjusts pricing).
3. Writes row to `llm_cost_log`.
4. Checks sum of `usd` for the current `run_id` against `DAILY_COST_CAP_USD` (env var, default `1.00`).
5. If cap would be exceeded: raises `CostCapExceededError`. Pipeline runner catches this, marks `pipeline_runs.status = "aborted_cost"`, composes digest from completed items, sends admin alert email.

### 13.2 Monthly cap

Checked at the start of each pipeline run: sum of `llm_cost_log.usd` for the current calendar month. If > `MONTHLY_COST_CAP_USD` (env var, default `18.00`), the run aborts before any LLM calls are made.

### 13.3 Prompt caching

Every reused system prompt prefix is structured to maximize Anthropic's prompt cache TTL (5 minutes — runs complete well within this window):
- **Cached:** taxonomy definitions, watchlist company list, style guide, few-shot examples.
- **Uncached:** item-specific content appended per call.
- Cache read tokens are priced at ~10% of base input token rate in `pricing.py`.

---

## 14. Admin Dashboard

### `/admin/` — Pipeline status

Last 7 pipeline runs: date, status (color-coded), items fetched, items in digest, total USD cost, duration. "Run Now" button (POST to `/admin/pipeline/run`). Current run status shown live if running.

### `/admin/sources` — Source health

Table: source name, type, last fetch time, status badge (OK / EMPTY / ERROR), consecutive failures, item count from last run. Sources with `is_flagged=1` highlighted in amber. "Test fetch" button per source (fires a single-source fetch and shows result).

### `/admin/costs` — Cost log

Daily cost breakdown by agent and model. Running month total vs. `MONTHLY_COST_CAP_USD`. Per-run drill-down table. Prompt cache hit/miss ratio shown.

### `/admin/users` — User management

User list: email, approval status, `is_admin` badge, last seen, email enabled. Approve/reject buttons for pending users. Link to user GDPR export.

---

## 15. GDPR Compliance

- **Export:** `GET /gdpr/export` returns a self-describing JSON package: user record, preferences, read log (up to 180 days), feedback signals.
- **Deletion:** `POST /gdpr/delete` cascades: deletes user row (`deleted_at` set, then hard-deleted on a 30-day cleanup job), preferences, read log, digest records. Feedback signals: `user_id` set to `null` (anonymized; signal value retained for ranking model integrity). Magic link tokens: deleted.
- **Retention:** `read_log` rows where `read_at < now - 180 days` are marked `pruned=1` and excluded from exports; a weekly APScheduler job hard-deletes pruned rows.
- **Logs:** no email addresses or user IDs appear in pipeline logs beyond what is operationally necessary (source health, cost tracking). `run_id` is used as the log correlation key.

---

## 16. Build Plan — Milestones

Each milestone is independently runnable, independently testable, and mergeable to `main` on its own. Branch naming: `git checkout -b m<n>-<slug>`.

---

### M1 — Skeleton

**Effort:** 3 half-days

**Goal:** A runnable end-to-end pipeline that loads `feeds/test-fixture/`, executes all agent stubs in sequence, writes records to SQLite, and exits cleanly. No real LLM calls. No real HTTP. Proves the architecture, data model, and interfaces are consistent before any real implementation.

**Deliverables:**
- `niche/` package scaffolded — all modules present with stub implementations.
- `feeds/test-fixture/` with synthetic config, sources, taxonomy, watchlist, prompts (obviously fake names: `AcmeBrake`, `FakeTier1Co`).
- All dataclasses in `niche/core/models/types.py`.
- SQLite schema creation in `niche/core/models/schema.py` (all tables, all columns, `feed_id` on every table).
- `FeedBundle` loader with validation against test-fixture.
- `Source` Protocol + `RawItem` dataclass.
- Pipeline runner threading `run_id` through all stages; logs entry/exit per stage.
- All 9 agents: stubs that return inputs unchanged (Classifier/Summarizer stubs produce synthetic fixed output).
- `cli.py` with all entry points: `pipeline run`, `agent <name>`, `bundle validate`, `admin promote`.
- `wsgi.py` returning a minimal Flask app (only `/health` endpoint).
- `requirements.txt` with all dependencies pinned.

**Test strategy:**
- `tests/integration/test_pipeline_end_to_end.py`: loads test-fixture, runs full pipeline stub, asserts `pipeline_runs` record exists with `status="complete"`, asserts `items` table has rows, asserts every items row has `feed_id` set, runs EP1 grep check against `niche/core/`.
- `tests/unit/test_feed_bundle_loader.py`: valid bundle loads without error; missing required key raises `BundleValidationError`.

**Definition of done:**
- `pytest tests/` passes with test-fixture loaded (brake-by-wire bundle not present, not referenced).
- `python cli.py bundle validate --feed-dir feeds/test-fixture` exits 0.
- `python cli.py pipeline run --feed-dir feeds/test-fixture` completes without exception.
- EP1 grep check in test suite passes.

---

### M2 — Sources

**Effort:** 4 half-days

**Goal:** All four source adapter types work with real implementations. Deduplication removes cross-source and cross-run duplicates. Feed bundle correctly instantiates real adapters from `sources.yaml`.

**Deliverables:**
- `RSSSource`, `GDELTSource`, `GoogleNewsSource`, `ScraperSource`, `RegulatorySource` — full `fetch()` implementations.
- Source factory with `SOURCE_REGISTRY`.
- Real deduplication stage: URL hash, title hash, fuzzy title similarity (`difflib`).
- `source_health` table updated after each source fetch attempt.
- Source retry logic: 3 attempts, 5 s exponential backoff.
- `tests/fixtures/`: local RSS XML and HTML files for adapter tests (no real HTTP in CI).

**Test strategy:**
- `tests/unit/test_dedup.py`: 20 items with known duplicates (URL, title, fuzzy) → assert correct de-dup behaviour; assert `is_duplicate=True` on the right items.
- `tests/integration/test_source_adapters.py`: each adapter tested against local fixture files using `httpx` mock; tests source failure path (adapter returns `[]`, `source_health` updated).
- Retry test: adapter raises on first two calls, succeeds on third; assert item count > 0 and no error logged.

**Definition of done:**
- All adapter and dedup tests pass.
- `python cli.py agent fetch --feed-dir feeds/test-fixture` prints a JSON list of `RawItem` objects.
- Two consecutive pipeline runs produce consistent dedup results (second run has no new unique items for the same fixture data).

---

### M3 — Classification and Tagging

**Effort:** 4 half-days

**Goal:** Classifier makes real Haiku calls with prompt caching. Company tagger matches against watchlist. Region classifier uses hybrid rule + LLM approach. Cost tracking populated.

**Deliverables:**
- `haiku_classifier.py` — real implementation with Anthropic SDK + prompt cache prefix.
- Real `classify-topic.md`, `classify-item-type.md` prompts in `feeds/test-fixture/prompts/` (with correct front-matter).
- Company tagger: string matching against watchlist `name` + `aliases`.
- Region classifier: rule-based primary; LLM fallback.
- `niche/core/cost/tracker.py` — full implementation writing to `llm_cost_log`.
- Daily cost cap check raising `CostCapExceededError` at the configured threshold.

**Test strategy:**
- `tests/unit/test_classify.py`: mocked Anthropic API response; assert correct `topic_tag`, `item_type` from synthetic items using test-fixture prompts.
- `tests/unit/test_cost_tracker.py`: assert `llm_cost_log` rows written correctly; assert `CostCapExceededError` raised when cap would be exceeded; assert daily cap check works across multiple calls.
- Integration tests gated behind `INTEGRATION_TESTS=1` env flag (use real API keys; not run in CI to avoid spending budget).

**Definition of done:**
- `python cli.py agent classify --feed-dir feeds/test-fixture --run-id <uuid>` classifies items in DB.
- All prompt files have correct front-matter.
- `llm_cost_log` contains entries after a run with correct token counts and USD.
- All mocked tests pass without real API keys.

---

### M4 — Summarization, Translation, and Ranking

**Effort:** 4 half-days

**Goal:** Real Haiku summarization with prompt caching. DeepL translation with Haiku fallback. Rule-based ranker producing ordered items. Digest composer writing `Digest` records with adaptive sizing.

**Deliverables:**
- `haiku_summarizer.py` — real implementation with `summarize.md` + `why-it-matters.md`.
- `deepl_translator.py` + `haiku_translator.py` behind `Translator` ABC (EP6).
- `niche/core/ranker/formula.py` — full scoring formula with all components.
- `niche/core/clusterer/rule_based.py` — tag-overlap clustering producing 3–5 clusters.
- Digest composer: 15-min read budget, 10–30 item bounds, cluster distribution.
- Real `summarize.md`, `why-it-matters.md`, `translate.md` prompts in test-fixture.

**Test strategy:**
- `tests/unit/test_ranker.py`: deterministic formula tests with known weights; assert score ordering; assert thumbs signal modifies ranking; assert keyword block removes item from results; assert company_boost elevates item.
- `tests/unit/test_composer.py`: 40 ranked items with known read times; assert digest has 10–30 items; assert sum of `read_time_min` ≈ 15 min.
- `tests/unit/test_clusterer.py`: items with known tag combinations; assert correct cluster assignment; assert 3–5 clusters produced.
- Translator tests: mock DeepL failure → assert Haiku fallback is called; mock both failures → assert `translation_failed=True` on item.

**Definition of done:**
- `python cli.py agent summarize --feed-dir feeds/test-fixture` produces `summary` and `why_it_matters` in DB.
- `python cli.py agent rank --feed-dir feeds/test-fixture` produces ordered items with `relevance_score` set.
- Full pipeline run with email stub produces a `Digest` record with correct `item_count` and `cluster_map`.
- Ranker unit tests pass without any LLM calls.

---

### M5 — Web UI

**Effort:** 5 half-days

**Goal:** A working web application with dark editorial UI. Users can log in via magic link, view today's digest with clusters and item cards, adjust preferences, submit thumbs feedback. Admin approval gated registration works end-to-end.

**Deliverables:**
- `niche/web/app.py` — `create_app(config)` factory wiring all blueprints, Flask-Login, CSRF, APScheduler.
- All six blueprints: `digest`, `auth`, `preferences`, `archive`, `api`, `admin` (dashboard-only for M5).
- `base.html` — dark editorial layout; feed theme injected via Jinja2 context vars (EP7).
- Item card template: all fields per §11.3.
- Magic-link auth flow end-to-end (requires `RESEND_API_KEY` in `.env`).
- Admin approval flow: notification email + one-click approval link.
- Preference wizard: region weights, topic weights, company watchlist, keyword boosts/blocks.
- Archive with keyword and date-range filter.
- `niche.css` — dark editorial stylesheet with CSS custom properties for accent color.
- `niche.js` — thumbs, filter tabs, mark-as-read via `fetch()`.
- `wsgi.py` — production WSGI entry point (`application = create_app()`).

**Test strategy:**
- `pytest-flask` test client: all blueprint routes return expected status codes (authenticated and unauthenticated paths).
- Auth flow: request magic link → verify token → assert session established; expired token → assert redirect with error.
- Preference save/load round-trip: POST preferences, GET preferences, assert values match.
- Filter API: POST three items with different `topic_tag`, GET with filter param, assert only matching items returned.
- Manual: responsive layout tested on desktop and mobile viewport in browser.

**Definition of done:**
- `flask --app wsgi:application run` starts without error.
- Full auth flow completes with Resend configured.
- Digest page renders with test-fixture data showing cluster groupings and item cards.
- Thumbs up/down persists to `feedback` table.
- All blueprint route tests pass.

---

### M6 — Email Digest and Admin Dashboard

**Effort:** 3 half-days

**Goal:** Daily email digest sent via Resend to all approved users. Full admin dashboard operational. GDPR export and deletion working. Admin CLI promotion working.

**Deliverables:**
- `resend_provider.py` — full implementation with 2-retry logic and `email_sent_at` update.
- `templates/email/digest.html` — inline-CSS email template; theme from `FeedBundle` (EP7).
- Email sender agent: per-user digest emails with read-signal click-through links.
- Unsubscribe flow: HMAC-signed link → `email_enabled=0`.
- Admin blueprint: source health table, user management (approve/reject), cost log, pipeline run trigger.
- Admin approval email with HMAC-signed one-click approval link.
- `GET /gdpr/export` and `POST /gdpr/delete` endpoints.
- `python cli.py admin promote --email=…` command.
- `read_log` pruning job registered with APScheduler (weekly, prune rows > 180 days).

**Test strategy:**
- Email template rendering: Jinja2 render test with synthetic digest data; assert no hardcoded feed-specific strings.
- Admin route authorization: assert non-admin users receive 403.
- GDPR export: assert all expected user data fields present in returned JSON.
- GDPR delete: assert cascade deletion across all `user_id` tables; assert feedback signals anonymized.
- Email sender: mock Resend client; assert correct payload sent; assert `email_sent_at` updated; assert double-send not possible.
- `admin promote` CLI: assert `is_admin=1` in DB after command.

**Definition of done:**
- Full daily run including email delivery works end-to-end on PythonAnywhere.
- Admin can view source health, trigger a run manually, and see cost log with per-agent breakdown.
- GDPR export and delete tested and confirmed cascade-correct.
- `python cli.py admin promote` works.

---

### M7 — Polish *(S-priority; implement if time permits)*

**Effort:** 3–4 half-days

**Deliverables (S-priority from PRD §4):**
- `S3.9` Saved-for-later: `saved_items` table (+ `feed_id`); UI toggle on item card; saved items list page.
- `S3.11` Shareable item links: HMAC-signed URL with `item_id`; opens item detail without auth for 7 days.
- `S3.13` Breaking-news ticker strip: horizontal scroll of `item_type=breaking` items; toggleable via JS; off by default.
- `S3.14` Accent color theme selector: red / blue / amber swatches; updates `--accent` CSS custom property via JS; persisted to `preferences`.
- `S4.4` Weekly trend digest: APScheduler weekly job; aggregates top items by thumbs signal for the past 7 days; separate email template.
- `S1.8` Admin "Add custom source" UI: URL input, test-fetch, tag assignment, enable toggle.

---

## 17. Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| **Press room scraper fragility** — HTML structure changes silently break selectors | High | Medium | Selector config lives in `sources.yaml` (EP1); fixing a broken scraper is a config change, not a code deploy. Source flagged unhealthy after 3 consecutive empty fetches. Admin alerted. |
| **Chinese source reliability** — MIIT, AutoNews China have inconsistent uptime | High | Low | These sources carry `source_weight=0.8`. Their failure does not block the pipeline. Multiple overlapping EN-language China-focused sources (CnEVPost, CarNewsChina, Gasgoo EN) provide redundancy. |
| **Translation cost drift** — more non-English items than estimated exhaust DeepL free tier | Medium | Medium | Characters consumed logged per run. Admin alert when monthly usage exceeds 400,000 chars (80% of 500K free limit). At that point: prioritize Chinese items (highest value) through DeepL; route German/Japanese to Haiku. |
| **$20 budget overrun** — more items or LLM calls than estimated | Low | High | Hard daily cap ($1.00 default) enforced in `cost/tracker.py` before the overrun occurs. Monthly cap ($18.00 default) checked at run start. Pipeline aborts and alerts admin. Price table in `pricing.py` updated when Anthropic adjusts rates. |
| **PythonAnywhere free tier — no persistent background process** | High | Medium | APScheduler requires always-on worker (PA Hacker plan, ~$5/month). Fallback: PA scheduled task calls POST `/admin/pipeline/run` via `curl` with admin API token. No PA-specific code in `core/`. |
| **PythonAnywhere memory limit** — ~512MB RAM on entry plan | Medium | Medium | Pipeline processes items sequentially. `body_raw` truncated to 1,000 chars at fetch time. Batch size configurable via env var (`PIPELINE_BATCH_SIZE`, default 10). |
| **SQLite write concurrency** — WSGI worker and APScheduler writing simultaneously | Medium | Medium | WAL mode enabled at startup. Single WSGI worker configured on PythonAnywhere (default). APScheduler jobs serialized. PipelineRunner acquires an application-level lock during batch writes. When >20 users signals Postgres readiness, the Repository interface makes it a one-file swap. |
| **Anthropic API rate limits** — Haiku tier-1 rate limit hit during batch classify/summarize | Low | Low | Items processed sequentially with a configurable inter-call delay (`LLM_CALL_DELAY_MS`, default 0). Retry-with-backoff handles transient 429s. |

---

## 18. Open Questions

The following items require user input before the relevant milestone begins. Each is noted with the earliest milestone it would block.

1. ~~**PythonAnywhere plan tier**~~ — **Resolved:** Hacker plan (always-on) confirmed. APScheduler embedded in WSGI process is the primary scheduling mechanism. The `curl`-based PA scheduled task fallback is not needed.

2. **DeepL API key** *(blocks M4)*: The free tier requires registration at deepl.com to obtain an API key. Is this already in place, or does it need to be set up? Free tier (500K chars/month) or paid?

3. **Resend sender domain** *(blocks M5)*: Resend requires a verified sending domain. What domain will be used? This determines `from_email` in `feeds/brake-by-wire/config.yaml` and whether the Resend EU endpoint can be used.

4. **`feeds/brake-by-wire/sources.yaml` real content** *(blocks M2 integration)*: Should real RSS URLs and press-room scraper configs be populated in M2 (so integration testing uses real sources) or deferred to a post-M6 QA pass against test-fixture only?

5. **Digest personalization depth** *(blocks M4 composer design)*: Should the Digest Composer re-run the full Ranker per user with their weights, or only re-sort the canonical top-30 using user weights? Re-running is more correct but writes up to 20 separate `Digest` rows per day.

6. **German UI translations** *(blocks M5)*: `ui_languages: ["en", "de"]` implies German translations for all UI strings (nav labels, button text, error messages, email subjects). Is there an existing translation resource, or should a `translations/de.json` file be populated from scratch during M5?

7. **Read-time floor** *(blocks M4 composer)*: For short regulatory items (title + one-line summary), `word_count / 200` may produce read times of < 0.5 minutes. Should a floor of 1 minute per item be applied when computing the 15-minute budget?

8. **Cluster label language** *(blocks M3/M4)*: The Clusterer calls Sonnet to generate cluster labels. Should labels be English-only (translated in UI if needed), or should Sonnet produce both EN and DE labels in a single call? Given the 10 Sonnet calls/day cap, a single bilingual call is feasible.

---

*SPEC.md is a living document. Changes after M1 kickoff go in an appendix with date and rationale rather than rewriting the original text, so milestone branches stay anchored to a known baseline. Significant architectural decisions are recorded in `DECISIONS.md`.*
