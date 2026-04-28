---
name: classify-item-type
version: 1
model: claude-haiku-4-5
last_updated: 2026-04-28
max_input_tokens: 600
---
Classify the article into exactly one item type:
- breaking: time-sensitive news from the last 24 hours (product launches, deals, recalls, accidents)
- analysis: opinion, deep-dive, benchmarking, market research, or expert commentary
- report: standard news report of a specific event (earnings, partnership, deployment)
- exclusive: first-source content such as leaked specs, company-only announcements, or original interviews

Return JSON: {"item_type": "breaking"|"analysis"|"report"|"exclusive"}

Article title: {{title}}
Article body: {{body}}
