# CLAUDE.md

Operating instructions for Claude Code in this repository. Read on every session.

---

## Project

Technical industry intelligence feed **platform**. First deployment: **brake-by-wire**. Designed as a reusable template for adjacent feeds (steer-by-wire, smart actuators, ADAS sensors, EV powertrain, etc.).

Read `PRD.md` for the full product brief. Read `SPEC.md` for technical architecture once it exists. If either file disagrees with what a user asks for in-session, ask — don't silently diverge.

**User context (important, affects editorial judgment):** Product owner is the CEO of a **Tier-2** brake-by-wire actuator supplier. Direct customers are Tier-1 system integrators (Bosch, Continental, ZF, Brembo, Hitachi Astemo, Mando, Knorr-Bremse, Nexteer, Hyundai Mobis, ADVICS, etc.). **Tier-1 news is at least as important as OEM news** — never collapse them into a single "suppliers" category.

---

## Non-negotiable architectural rules

Condensed from PRD §7. Violating any without explicit discussion is a bug, not a shortcut.

- **EP1** No hard-coded domain strings in core code. No company names, source URLs, regulatory bodies, topic labels, or language-specific strings in `core/`. Those live in `feeds/<domain>/` bundles and UI translation files.
- **EP2** Every source type implements the same `Source.fetch() → [RawItem]` interface. RSS, GDELT, NewsAPI, scraper — same contract.
- **EP3** Pipeline stages are pure functions: `stage(items, config) → items`. Stateless, composable, individually testable.
- **EP4** Prompts live in versioned `.md` files under `feeds/<domain>/prompts/`. Never inline a prompt in source code.
- **EP5** Every persisted record carries `feed_id` from day one. Schema, ORM, API responses — all of it. v1 has one feed; the schema assumes many.
- **EP6** Ranker, summarizer, translator, email provider, storage layer each sit behind a narrow interface. Swapping providers must be a one-file change.
- **EP7** UI components accept feed theme (name, tagline, accent color, logo) as props. Core components are generic.
- **EP8** Ranker operates on tags, weights, and user signals. No domain logic inside the ranker.
- **EP9** Auth, translation, storage, scheduling, email, cost tracking are platform-level. Feeds never re-implement them.
- **EP10** Tests run against `feeds/test-fixture/` with synthetic sources. If the suite passes without the brake-by-wire bundle loaded, the code is genuinely generic.

Apply these at extension seams. Do not over-abstract internal helpers that have nothing to do with domain or provider swapping.

---

## Workflow rules

- **New work starts in plan mode.** Propose the plan, get approval, then execute.
- **One milestone at a time.** Implement the milestone in `SPEC.md`, then stop. Wait for review. Do not roll into the next milestone proactively.
- **Tests before implementation** for pipeline stages, source adapters, and any `core/` module. UI and config loading can be test-after.
- **Every agent has a CLI entry point.** Summarizer, ranker, fetcher, translator, classifier must each be runnable standalone for debugging. E.g. `agent summarize --item-id=123`.
- **Never expand scope without asking.** If you notice something worth doing that wasn't requested, append it to `NOTES.md` and mention it at the end of your response. Do not implement.
- **Branch per milestone.** `git checkout -b m<n>-<slug>` before starting. Merge to main only after milestone approval.
- **Commit frequently, one logical change per commit.** Reference the milestone: `M2: add RSS source adapter`.

---

## Code conventions

- **Language and framework**: defined in `SPEC.md` once the host is chosen. Do not assume.
- **Configuration**: YAML for feed bundles, `.env` for secrets. Never mix.
- **Prompts**: one prompt per file, with a header block:
  ```
  ---
  name: summarize
  version: 3
  model: claude-haiku-4-5
  last_updated: 2026-04-25
  ---
  ```
- **Logging**: structured JSON. Every pipeline run has a `run_id` threaded through every log line.
- **Error handling**: source fetch failures must not crash the pipeline. Log, flag the source unhealthy, continue.
- **No silent fallbacks**: if translation fails, mark the item `translation_failed=true` and surface it; do not serve the foreign-language text as if it were translated.

---

## LLM usage policy

Monthly budget is **$20 hard ceiling**. Token spend is a real constraint.

- **Default model**: Claude Haiku (current: `claude-haiku-4-5`) for summarization, translation, classification, why-it-matters.
- **Sonnet allowed for**: daily thematic clustering across items, editor's-pick lead blurb. At most ~10 calls/day total.
- **Opus: never.** Out of budget.
- **Prompt caching**: use it for anything reused across items in a run — taxonomy, style guide, few-shot examples belong in cached prefixes.
- **Cost tracking**: persist per-call cost with `run_id`, `model`, `input_tokens`, `output_tokens`, `usd`. The admin dashboard needs this.
- **Fail closed on cost**: if a daily run would exceed a configured per-day cost cap, stop and alert. Do not silently overrun.

---

## Feed bundle layout

```
feeds/
  brake-by-wire/
    config.yaml           # feed name, tagline, languages, accent color
    sources.yaml          # RSS URLs, API endpoints, regulatory feeds
    taxonomy.yaml         # topics, regions, item-types, value-chain roles
    watchlist.yaml        # seed companies with role + relationship tags
    prompts/
      summarize.md
      classify-topic.md
      classify-item-type.md
      why-it-matters.md
      translate.md
  test-fixture/           # synthetic feed used only for tests
```

---

## Adding common things (cookbook)

- **New source (existing type):** one entry in `feeds/<domain>/sources.yaml`. No code.
- **New source type (new API or protocol):** adapter in `core/sources/` implementing the `Source` interface + tests + factory registration.
- **New pipeline stage:** pure function in `core/pipeline/`, registered in the stage list, tested against `feeds/test-fixture/`.
- **New feed domain:** copy `feeds/test-fixture/` to `feeds/<new-domain>/`, fill in config, taxonomy, sources, watchlist, prompts. Run the feed-bundle validator before first load.
- **New UI language:** add translation file, extend language enum, no component changes.
- **New LLM prompt:** new `.md` file under `feeds/<domain>/prompts/` with the header block. Reference by name, never by path.

---

## Secrets and config

- `.env.example` is committed. `.env` is not. `.gitignore` must enforce this.
- API keys (Anthropic, Resend, any aggregator) live in `.env`. Never commit, never hard-code, never print in logs.
- Feed config is non-secret and may be public. A feed bundle must never contain secrets.
- On Synology deployment, secrets come from the host's environment, not files in the repo.

---

## GDPR and privacy

EU users. Treat these as first-class requirements, not afterthoughts:

- **Exportable**: an admin endpoint returns a user's full record (preferences, read history, feedback) as JSON.
- **Deletable**: one-click cascade delete across all tables carrying `user_id`.
- **Retention**: read logs older than 180 days are auto-pruned. Feedback signals (thumbs) are retained but anonymized after the user deletes their account.
- **Logs**: never log PII beyond what's operationally necessary. No email addresses in pipeline logs.

---

## When to stop and ask

Hard stops — do not proceed without user input:

- Adding a library not already in dependencies.
- Modifying a core interface (`Source`, `PipelineStage`, `Ranker`, `Storage`).
- Any change to the data model after M3.
- Adding a new feed domain (user decides when that happens).
- Any cost-affecting decision (model choice, polling frequency, batch size, new LLM call site).
- Anything touching auth, secrets, or production data.
- A requirement in PRD/SPEC that seems wrong or contradictory — flag it, don't work around it.

---

## Anti-patterns

- **Do not over-engineer internals.** EP rules apply at extension seams (new feeds, new sources, new providers). Internal helpers don't need abstract interfaces.
- **Do not add dependencies casually.** Each one is maintenance cost. Prefer stdlib or existing deps.
- **Do not run scripts against production data without approval.** Live SQLite, real emails, real API calls need an explicit go-ahead.
- **Do not assume user intent on ambiguity.** Ask. Once.
- **Do not generate mock data that looks real.** Test fixtures use obviously-synthetic company names (`AcmeBrake`, `FakeTier1Co`), never real ones.

---

## Commands

To be filled in after `SPEC.md` fixes the stack:

- Run tests: `TBD`
- Run the daily pipeline locally: `TBD`
- Run a single agent: `TBD`
- Validate a feed bundle: `TBD`
- Start the web app locally: `TBD`

---

## Housekeeping

- Update this file when SPEC.md fixes decisions (stack, commands, key paths).
- Record significant architectural decisions in `DECISIONS.md` (one-line entries with date).
- `NOTES.md` is for deferred ideas, not decisions. Review it at every milestone boundary.
