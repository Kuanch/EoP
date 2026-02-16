# Hybrid Threat Detection Design

**Date:** 2026-02-16
**Status:** Approved

## Overview

Two-pass threat scoring: configurable keyword rules as fast filter, Claude Haiku as contextual second pass. New "Threats" tab in dashboard with live feed and full config UI.

## Architecture

```
Collectors → threat_engine.assess() → rule score ≥ llm_threshold?
                                            ↓ yes
                                       Haiku LLM call → structured verdict
                                            ↓
                                       threat feed + ntfy (if ≥ notify_threshold)
```

## Config: `threat_rules.json`

```json
{
  "keyword_rules": { "war": 10, "nuclear": 10, "missile": 9, ... },
  "llm_threshold": 5,
  "notify_threshold": 7,
  "llm_enabled": true,
  "llm_prompt": "You are a geopolitical threat analyst...",
  "cooldown_minutes": 15,
  "sources": { "news": true, "cyber": true, "pizzint": true }
}
```

## Dashboard Tab

New "Threats" tab with:
1. **Threat Feed** — live table (time, source, title, rule score, LLM score, rationale, notified)
2. **Config Panel** — keyword rules editor, threshold sliders, LLM prompt textarea, source toggles
3. **Stats** — threats today, notifications sent, LLM calls made

## Backend

- `threat_engine.py` — rule scoring, Haiku calls, feed management
- `/api/threats/config` GET/POST — read/update config
- `/api/threats/feed` GET — recent assessments
- Collectors call `threat_engine.assess()` after each collection

## Cost

~2000 Haiku calls/day ≈ $0.01-0.05/day
