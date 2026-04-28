---
name: translate
version: 2
model: claude-haiku-4-5
last_updated: 2026-04-28
max_input_tokens: 1000
---
Translate the following article to English. Preserve factual accuracy and professional tone.
Return a JSON object with two fields: "title" and "body".
Return only valid JSON. No extra text.

Source language: {{language}}
Title: {{title}}
Body: {{body}}
