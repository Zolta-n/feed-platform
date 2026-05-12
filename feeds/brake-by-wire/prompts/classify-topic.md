---
name: classify-topic
version: 1
model: claude-haiku-4-5
last_updated: 2026-04-28
max_input_tokens: 600
---
Classify the article into exactly one topic and one item type.

Topics: tier1, oem, regulation, technology
Item types: breaking, analysis, report, exclusive
Regions: americas, europe, asia

Return JSON only:
{"topic_tag": "<topic>", "item_type": "<type>", "region_tag": "<region>"}

If unsure, use "report" for item_type and null for region_tag.
