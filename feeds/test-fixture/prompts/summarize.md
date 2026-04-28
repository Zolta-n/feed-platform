---
name: summarize
version: 1
model: claude-haiku-4-5
last_updated: 2026-04-28
max_input_tokens: 800
---
Summarize the following article in 2-3 sentences. Return JSON: {"summary": "...", "why_it_matters": "one line"}.

Article:
{{body}}
