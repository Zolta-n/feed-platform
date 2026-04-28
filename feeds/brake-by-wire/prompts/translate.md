---
name: translate
version: 1
model: claude-haiku-4-5
last_updated: 2026-04-28
max_input_tokens: 1200
---
Translate the following automotive industry article into English. Preserve technical terms, company names, and product names exactly. Return a JSON object with exactly two fields:
- "title": the translated title
- "body": the translated body text

Return only valid JSON. No extra text, no markdown fences.

Source language: {{source_language}}
Title: {{title}}
Body: {{body}}
