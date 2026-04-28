# PRD: Technical Industry Intelligence Feed Platform

_First deployment: brake-by-wire. Designed to be re-used as a template for adjacent feeds (steer-by-wire, smart actuators, ADAS sensors, EV powertrain, etc.). See §9._

**Version:** 0.2 (draft)
**Owner:** [CEO, brake-by-wire actuator company]
**Status:** Pre-implementation

---

## 1. Problem

As CEO of a company producing brake-by-wire actuators, staying current on market, regulatory, and technology developments across three regions consumes 30+ minutes per day today and still misses relevant signals. Manual monitoring of trade press, regulatory sites, company announcements, and Chinese industry sources is fragmented and unreliable. No existing tool combines the domain filter, multi-region coverage, and relevance learning needed for this niche.

## 2. Users

- **Primary:** CEO of a **Tier-2** brake-by-wire actuator supplier (product owner, most frequent user). Sells to Tier-1 system integrators (Bosch, Continental, ZF, Brembo, Hitachi Astemo, Mando, etc.), who in turn sell complete brake systems to OEMs.
- **Secondary:** 5–20 colleagues at the same company — engineering leads, product managers, sales/BD, strategy.
- **Context of use:** Desktop or mobile, ~15 minutes per session, any time of day (morning preferred). Email digest serves as the push channel.
- **Access model:** Internet-accessible application hosted on a private web server (Synology NAS or PythonAnywhere). Sign-up by email with admin approval. No open public registration.

## 3. Goals and Non-Goals

### Goals (v1)
- Deliver a daily, curated feed of relevant brake-by-wire news readable in ≤15 minutes.
- Cover **Tier-1 activity, OEM activity, regulation, and technology** across **Americas, Europe, Asia**. Tier-1 is first-class because Tier-1s are the direct customers and frequent competitors of a Tier-2 actuator supplier.
- Allow per-user preferences for regions, topics, and a company watchlist (customers, competitors, suppliers).
- Learn per-user preferences via thumbs up/down and read signals.
- Translate foreign-language sources (German, Chinese, Japanese) into the user's preferred UI language.
- Deliver via web UI and optional daily email newsletter.
- Run within a **$20/month total budget** on a private server.
- **Template-ready architecture:** the same codebase must be reusable for adjacent technical feeds (steer-by-wire, smart actuators, etc.) via configuration only, with no core code changes. See §9.
- **Modular internals:** every major component (source adapters, translation, ranker, summarizer, email, storage) must be replaceable in isolation without ripple effects elsewhere.

### Non-Goals (v1)
- Podcast generation (v2).
- LinkedIn, WeChat, X/Twitter content (v2 — require paid aggregators).
- Analyst report ingestion (v2 — manual upload only if needed).
- Social features: comments, threaded discussion, public sharing.
- Native mobile apps (responsive web is sufficient).
- Real-time push notifications / breaking-news alerts (v2 consideration).
- **Multiple concurrent feeds in one deployment (v2).** v1 ships as a single-feed deployment (brake-by-wire). A second feed is created by cloning the repo and swapping the config bundle — not by adding a feed inside a running instance. The architecture does not block a future multi-feed runtime (see §9), but it is not a v1 goal.

## 4. Functional Requirements

Prioritization: **M = must-have v1**, **S = should-have v1 if time permits**, **C = could-have / v2**.

> **Implementation note:** every requirement below must be implemented in accordance with the extensibility principles in §7. Where a requirement names brake-by-wire-specific sources, taxonomies, or companies, those belong in the feed config bundle (`feeds/brake-by-wire/`), not in core code.

### Content acquisition
- **M1.1** Pull from RSS feeds of trade press, company blogs, and industry publications.
- **M1.1a** Pull from Tier-1 press rooms and investor relations pages (Bosch, Continental, ZF, Brembo, Hitachi Astemo, Mando, Knorr-Bremse, Nexteer, Hyundai Mobis, ADVICS, etc.) — RSS where available, polite polling of press-release pages otherwise.
- **M1.1b** Pull from OEM press rooms for brake-program-relevant announcements (VW Group, Stellantis, GM, Ford, Toyota, Honda, BYD, Tesla, BMW, Mercedes, Hyundai-Kia, and others configured in watchlist).
- **M1.2** Pull from GDELT (free global news event database) for broad coverage.
- **M1.3** Pull from Google News via RSS queries.
- **M1.4** Pull from free Chinese automotive sources: CnEVPost, CarNewsChina, Gasgoo (EN), AutoNews China, China Daily auto section, MIIT announcements.
- **M1.5** Pull from regulatory bodies: NHTSA (US), EU type-approval bulletins, UNECE WP.29, MIIT (China), MLIT (Japan), KATRI (Korea).
- **M1.6** Pull from patent RSS: EPO, Google Patents.
- **M1.7** Run pipeline on a daily schedule (default 05:00 local) plus manual trigger.
- **S1.8** Admin can add a custom RSS source via URL with test-fetch and tagging.

### Processing and curation
- **M2.1** Deduplicate across sources via URL, title similarity, and content hash.
- **M2.2** Classify each item by region (Americas / Europe / Asia) using source origin and content signals.
- **M2.3** Classify each item by topic: **Tier-1 / OEM / regulation / technology**. Tier-1 and OEM are distinct because a Tier-2 supplier's decisions depend on both tiers separately (customer signals vs. end-demand signals).
- **M2.3a** Classify each item by item-type for presentation: **breaking** (time-sensitive, <24h), **analysis** (deep-dive, opinion, benchmarking), **report** (primary reporting of a specific event), **exclusive** (first-source content, e.g. leaked specs, company-only announcements).
- **M2.4** Tag each item with detected company names from the configurable watchlist. Each company in the watchlist carries two orthogonal tag dimensions: **value-chain role** (OEM / Tier-1 / Tier-2 peer / supplier) and **relationship** (customer / competitor / partner / prospect / watch). A single company may hold multiple relationship tags (e.g. Bosch = Tier-1, customer + competitor).
- **M2.5** Translate non-English items into the user's UI language (English / German / Chinese).
- **M2.6** Generate a 2–3 sentence summary plus a one-line "why it matters" per item.
- **M2.7** Score per-user relevance from preferences + learned signal.
- **M2.8** Group related items into 3–5 thematic clusters for the daily digest.

### Consumption — web
- **M3.1** Today's digest: grouped by thematic cluster, highest-relevance cluster first. Primary nav tabs: **ALL / TIER-1 / OEM / TECHNOLOGY / REGULATION** (tab order is config-driven per §7).
- **M3.2** Item card: item-type badge (breaking/analysis/report/exclusive), category tag, title, summary, why-picked, source, timestamp, estimated read time, region/topic/company tags.
- **M3.3** Item detail view: full summary, translation note, link to original.
- **M3.4** Thumbs up / thumbs down per item.
- **M3.5** Mark as read (automatic on click + explicit option).
- **M3.6** Filter the digest by region, topic, company.
- **M3.7** Archive with search by keyword, company, date.
- **M3.8** Responsive design for desktop and mobile web.
- **S3.9** Saved-for-later list.
- **S3.10** "More like this" button on an item.
- **S3.11** Shareable item link for forwarding to colleagues.
- **S3.12** Grid density toggle (comfortable / compact).
- **S3.13** Breaking-news ticker strip at top of digest (toggleable).
- **S3.14** Accent color theme selector (red / blue / amber).

### Consumption — email
- **M4.1** Daily email newsletter with top N items (N configurable per user).
- **M4.2** Per-user send-time configuration.
- **M4.3** Unsubscribe / pause.
- **S4.4** Weekly trend digest option.

### Configuration
- **M5.1** Preferences page: region weights (Americas / Europe / Asia), topic weights (Tier-1 / OEM / regulation / technology), company watchlist with value-chain role tags (OEM / Tier-1 / Tier-2 peer / supplier) and relationship tags (customer / competitor / partner / prospect / watch), keyword boosts and blocks.
- **M5.2** UI language preference: English (default), German, Chinese.
- **M5.3** Email preferences: enable/disable, send time, item count.
- **M5.4** Preferences persisted per user.

### Auth and admin
- **M6.1** Sign-up with email via magic link (no password).
- **M6.2** Admin-approved registration.
- **M6.3** Admin role with source management.
- **M6.4** Admin dashboard: source health, pipeline status, daily cost/usage.

### Operations
- **M7.1** Source health monitoring: flag broken or empty feeds.
- **M7.2** Run history and logs.
- **M7.3** API cost tracking per day.

### v2 candidates (explicitly deferred)
- **C1** Podcast generation: 5–15 minute daily briefing via TTS, delivered through a private podcast RSS feed.
- **C2** LinkedIn company page content via a paid aggregator.
- **C3** WeChat public account content via a paid aggregator.
- **C4** X/Twitter content via paid API tier.
- **C5** Manual analyst-report upload with PDF extraction.
- **C6** Push notifications for breaking news.
- **C7** Team annotations / shared highlights.
- **C8** Custom alert rules (e.g. "notify me when [company] announces [keyword]").

## 5. User Flows

### Flow 1: First-time user onboarding
1. User receives an invitation email.
2. Clicks the link, enters their email, receives a magic link.
3. Admin is notified and approves in one click.
4. User completes the preference wizard: regions, topics, company watchlist (seeded with sensible defaults for brake-by-wire).
5. Lands on today's digest.

### Flow 2: Daily consumption (primary)
1. User opens the app or clicks through from email.
2. Sees today's digest: header with date and "X items, ~Y min read."
3. Items grouped into 3–5 thematic clusters; highest-relevance cluster first.
4. User skims, clicks into 2–3 items for full summary.
5. Thumbs up/down as they go (feeds tomorrow's ranking).
6. Clicks to original source for 1–2 items they want to read deeply.

### Flow 3: Email consumption
1. User receives email at configured time (default 06:30).
2. Subject line: "[Date] Brake-by-Wire Brief — top N items."
3. Email mirrors web digest structure; click-through counts as a read signal.
4. Back-link opens the web app for the full digest.

### Flow 4: Preference adjustment
1. User notices irrelevant items surfacing.
2. Goes to Preferences, adjusts topic weights or company watchlist.
3. Saves; next digest reflects the change.

### Flow 5: Archive and research
1. User recalls an item from last week about a specific competitor.
2. Uses search, or filters archive by company + date range.
3. Finds the item, optionally shares the link with a colleague.

### Flow 6: Admin — adding a new source
1. Admin finds a new relevant RSS feed.
2. Goes to Admin → Sources → Add, enters the URL.
3. Test-fetch runs; admin assigns default region/topic tags and enables the source.
4. Source joins the next daily run.

## 6. Constraints

- **Hosting:** Synology NAS (Docker-capable, preferred) or PythonAnywhere (Python-only, simpler deploy). Stack choice must be compatible with the chosen host. Public HTTPS.
- **Budget:** ≤$20/month total running cost. No paid data-source subscriptions in v1.
- **Compliance:** GDPR applies (EU colleagues). Preferences and reading history must be exportable and deletable on request. Privacy page required.
- **Data residency:** Prefer EU-based services where available (e.g. Resend EU region, Anthropic EU endpoint).
- **Scale:** 5–20 concurrent users, ~50–150 items/day ingested, ~30 items/day in a user's final digest.
- **Security:** Magic-link auth, admin-approved registration, HTTPS only, secrets stored in environment variables / Synology Secrets Manager.
- **Languages:** English default, German and Chinese optional for UI. All three for ingestion via translation.

## 7. Extensibility & Modularity

The v1 deployment targets brake-by-wire, but this is the first instance of what must be a **generic, re-usable feed platform**. The architecture treats domain specifics (brake-by-wire vocabulary, specific sources, specific companies) as **configuration**, not code. Deploying a second feed — steer-by-wire, smart actuators, ADAS sensors, EV powertrain — should require editing config files and prompts only, not modifying pipeline logic.

This is a first-class requirement, not an aspiration. The SPEC.md derived from this PRD must enforce it.

### 7.1 Domain-as-configuration

Each feed domain is a self-contained bundle:

```
feeds/
  brake-by-wire/
    config.yaml          # feed name, tagline, languages, accent color
    sources.yaml         # RSS URLs, API endpoints, regulatory feeds
    taxonomy.yaml        # topics, regions, item-types, tag colors
    watchlist.yaml       # seed companies (customers, competitors, suppliers)
    prompts/
      summarize.md
      classify-topic.md
      classify-item-type.md
      why-it-matters.md
      translate.md
  steer-by-wire/         # future — same structure
  smart-actuators/       # future — same structure
  test-fixture/          # synthetic feed used only for tests
```

Core code loads the active feed bundle at startup. **No core module imports anything domain-specific.**

### 7.2 Architectural rules (non-negotiable)

- **EP1 — No hard-coded domain strings in core code.** Specific company names, product categories, regulatory body names, source URLs must never appear in pipeline, ranking, storage, or UI modules. They live only in config bundles and UI translation files. Enforceable via a grep-based check in CI.

- **EP2 — Source adapters behind a common interface.** Every source type (RSS, GDELT, NewsAPI, custom scraper) implements the same `Source.fetch() → [RawItem]` contract. Adding a new source type = writing one adapter. Adding a new source instance = one line of config.

- **EP3 — Pipeline stages are stateless and composable.** Fetch → dedupe → classify → translate → summarize → tag → rank. Each stage is a pure function over items. Reordering, skipping, or inserting a stage is a pipeline-config change, not code.

- **EP4 — Prompts live in versioned `.md` files**, never inlined in code. Each prompt carries a version header. Prompts are per-feed with a fallback to platform defaults. Tuning a prompt never requires a code deploy.

- **EP5 — Data model carries `feed_id` from day one.** Every persisted record (item, user preference, digest, feedback signal, read log) has a `feed_id` column. v1 has one feed but the schema is unchanged when a second is added. This avoids a painful migration later.

- **EP6 — Component contracts over component implementations.** Ranker, summarizer, translator, email provider, storage layer — each sits behind a small interface. Swapping Claude Haiku for a local model, Resend for Mailgun, SQLite for Postgres, or the rule-based ranker for an embeddings-based one must be a single-file change.

- **EP7 — UI components accept feed theme as props.** Feed name, tagline, accent color, logo come from config. Core components (card, digest grid, preference page, email template) are generic. Re-skinning for a new feed = editing the feed's `config.yaml`.

- **EP8 — Ranking logic is tag-driven, not domain-driven.** The ranker operates on tags, weights, and user signals. Domain-specific relevance is encoded in the taxonomy and watchlist, not in ranker code.

- **EP9 — Shared infrastructure stays shared.** Auth, translation, storage, scheduling, email delivery, cost tracking are platform-level and feed-agnostic. A feed bundle never re-implements infrastructure.

- **EP10 — Test against a synthetic feed.** Unit and integration tests run against `feeds/test-fixture/` with fake sources and fake content. If tests pass without the brake-by-wire bundle loaded, the code is genuinely generic.

### 7.3 What this buys and what it costs

**Buys:**
- Launching a steer-by-wire or smart-actuator feed later is ~1 day of config + prompt tuning, not a fork-and-diverge.
- Bug fixes and model upgrades benefit all feeds simultaneously.
- A teammate can contribute a new feed without understanding the whole codebase.
- Clear, enforceable test surface.

**Costs:**
- Slightly more upfront design work (interfaces, config loader, schema with `feed_id`).
- One extra level of indirection in a few places (load taxonomy from config instead of hard-coding three topics).
- Discipline required: apply these rules at the extension seams, not everywhere — don't over-engineer internal helpers that have nothing to do with domain logic.

### 7.4 Naming implication

**BrakeByWire** is the feed-level brand rendered from `feeds/brake-by-wire/config.yaml`. The platform internal identity is **Niche** — used in code namespaces, Docker image names, repo references, and the admin dashboard. Each deployed feed renders its own brand (BrakeByWire, SteerWire, ActuatorBeat, …) from config.

## 8. Success Metrics

### Product
- ≥80% of invited colleagues register and use the app at least 3× in their first 2 weeks.
- Median active user opens the digest ≥4 days/week after week 2.
- Median digest session ≤15 minutes.
- ≥60% of surfaced items are not thumbs-downed.

### Technical
- Daily pipeline run completes in <30 minutes.
- ≥90% of configured sources return content on any given run.
- Uptime ≥99% over any 30-day window.
- Monthly running cost stays under $20.

### Qualitative
- CEO self-report: "I find ≥1 actionable impulse per week from the feed."
- Colleague self-report: "This replaces at least 15 minutes/day of my previous manual monitoring."

## 9. Open Questions

_All pre-SPEC open questions resolved. See Resolved section below._

### Resolved
- **Platform name:** Niche (internal identity — namespaces, Docker images, admin dashboard).
- **Feed brand:** BrakeByWire (rendered from `feeds/brake-by-wire/config.yaml`; future feeds render their own brand).
- **Hosting:** PythonAnywhere for MVP (Python-only, WSGI, no Docker); architecture kept portable for later migration to Synology (Docker Compose). No PythonAnywhere-specific calls in `core/`.
- **Admin identity:** `is_admin` flag on the user table; promoted via CLI (`agent admin promote --email=...`). No admin-management UI in v1.
- **Translation:** DeepL primary for all non-English content (Chinese, German, Japanese → English); Claude Haiku fallback on DeepL failure. UI languages: English and German only (Chinese UI deferred).
- **Digest size:** Adaptive to ~15-min read (est. read time per item), minimum 10 items, maximum 30 items.
- **Clustering:** Rule-based (topic tag + company tag overlap) for v1; semantic embeddings deferred.
- **Ranker v1:** `source_weight × topic_weight × company_boost + recency_decay + thumbs_signal`. All weights in taxonomy/preferences; no domain logic in ranker code.
- Registration: open email sign-up with admin approval.
- Watchlist seed (split by value-chain role):
  - **Tier-1 (customers + competitors):** Bosch, Continental, ZF, Brembo, Hitachi Astemo, Mando, Knorr-Bremse, Nexteer, Hyundai Mobis, ADVICS, Haldex.
  - **OEM (end-demand signal):** VW Group, Stellantis, GM, Ford, Toyota, Honda, BYD, Nio, XPeng, Tesla, BMW, Mercedes, Hyundai-Kia, Geely, SAIC, Li Auto.
  - **Tier-2 peers:** to be populated by user (segment-specific).
- Regulatory scope: US (NHTSA), EU (UNECE WP.29, type-approval), China (MIIT), Japan (MLIT), Korea (KATRI).
- Topic taxonomy: **Tier-1 / OEM / regulation / technology** (four categories — Tier-1 elevated because it represents direct customers for a Tier-2 supplier).
- Item-type taxonomy: breaking / analysis / report / exclusive.
- Mockup reference: received — see Design Appendix.

---

## Appendix A: Design Direction

Based on initial mockup (BrakeByWire — Industry Intelligence):

- **Aesthetic:** dark editorial, Bloomberg / The Information-adjacent. High contrast, generous whitespace.
- **Typography:** bold condensed or serif headlines; uppercase monospaced labels and tags.
- **Color system:**
  - Item-type badges: breaking = amber, analysis = blue, report = red, exclusive = green.
  - Category tags (REGULATION, SUPPLIERS, OEM) rendered as monospaced uppercase labels next to the type badge.
  - User-selectable accent color (red / blue / amber) applied to CTAs and active states.
- **Layout:** card grid, 1–3 columns responsive. Breaking-news ticker strip optional at top.
- **Per-item metadata visible on card:** author or source initials avatar, estimated read time, timestamp, tags.
- **Header:** logo + tagline ("Industry Intelligence"), search, sign-in / subscribe (becomes "Request Access" for this invite-only deployment).
- **Primary nav tabs:** ALL / TIER-1 / OEM / TECHNOLOGY / REGULATION.
- **Settings affordances visible in mockup:** "Tweaks" panel for grid density, ticker on/off, accent color — lightweight personalization without a full settings page.

_Design is a reference, not a binding spec. Final visuals to be confirmed during SPEC.md / design iteration._

---

_This PRD is a living document. Changes after v1 kickoff go in an appendix with date + rationale rather than rewriting the original, so the SPEC.md stays anchored to a known baseline._
