---
name: classify-item-type
version: 1
model: claude-haiku-4-5
last_updated: 2026-04-28
max_input_tokens: 400
---
Classify the article as: brief (short news item) or deep (in-depth analysis).
Return JSON: {"item_type": "brief"|"deep"}.

Article title: {{title}}
