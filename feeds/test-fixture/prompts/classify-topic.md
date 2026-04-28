---
name: classify-topic
version: 1
model: claude-haiku-4-5
last_updated: 2026-04-28
max_input_tokens: 600
---
Classify the article into one topic: technology, market.
Return JSON: {"topic": "technology"|"market"}.

Article title: {{title}}
Article body: {{body}}
