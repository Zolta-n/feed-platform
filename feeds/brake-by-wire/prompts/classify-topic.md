---
name: classify-topic
version: 1
model: claude-haiku-4-5
last_updated: 2026-04-28
max_input_tokens: 600
---
Classify the article into exactly one topic from this list:
- tier1: news about Tier-1 automotive system integrators (Bosch, Continental, ZF, Brembo, Hitachi Astemo, Mando, Knorr-Bremse, Nexteer, Hyundai Mobis, ADVICS, Aptiv, etc.)
- oem: news about automotive OEMs (VW, Toyota, Tesla, BMW, Mercedes, GM, Ford, Stellantis, BYD, Hyundai, etc.)
- regulation: safety regulations, technical standards, NHTSA, EU type approval, UN ECE, FMVSS, homologation
- technology: engineering, R&D, patents, new braking technologies, software, sensors, actuators

Return JSON: {"topic": "tier1"|"oem"|"regulation"|"technology"}

Article title: {{title}}
Article body: {{body}}
