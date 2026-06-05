# Deferred Ideas

Review at every milestone boundary. Items here are not decisions — they are possibilities worth considering.

## Todo

- [done] Minimum 3 items per topic category: `_MIN_ITEMS_PER_TOPIC = 3` added to `compose.py` `_select_items()`. A dedicated top-up pass (Step 2) runs after cluster-representative selection and before the global fill, ensuring OEM/Regulation/Technology/Tier-1 tabs each show ≥ 3 articles when that many are available in the ranked pool.
- [ ] Synology NAS deployment (Docker + GHCR + Watchtower + Cloudflare Tunnel, mirroring the `reporting` repo). Full plan saved at `~/.claude/plans/delegated-crafting-hippo.md`. Adds Dockerfile/compose/GH Actions + gunicorn dep; exposes `bbw.businessintels.com` on host port 8001; daily run via DSM Task Scheduler. Not yet executed.
