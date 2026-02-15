# ntfy Push Notifications Design

**Date:** 2026-02-16
**Status:** Approved

## Overview

Add self-hosted ntfy push notification support to EoP so critical events trigger iPhone alerts.

## Architecture

```
Collectors → notifier.send() → HTTP POST → ntfy server (:8090) → iPhone app
```

- **ntfy server**: Self-hosted via Docker on port 8090
- **notifier.py**: Async module with `send_notification(title, message, priority, tags)`
- **Cooldown**: Per-topic, 15-minute window to prevent spam
- **Config**: `NTFY_URL` and `NTFY_TOPIC` in `.env`

## Notification Triggers

| Source | Condition | Priority |
|--------|-----------|----------|
| News | threat_score > 5 | high |
| Threat scoring | region score > 60 | urgent |
| Cyber | severity Critical or High | high |
| PizzINT | threat level change | high |

## Components

1. **Docker compose** for ntfy server (port 8090, persistent data in `data/ntfy/`)
2. **`notifier.py`** — async POST to `{NTFY_URL}/{NTFY_TOPIC}`, cooldown dict, priority mapping
3. **Collector hooks** — call `notifier.send()` when thresholds exceeded
4. **Config** — `NTFY_URL=http://localhost:8090`, `NTFY_TOPIC=eop-alerts`

## Non-Goals

- No UI for notification settings (future)
- No per-user notification preferences (future)
- Threshold tuning deferred to after initial testing
