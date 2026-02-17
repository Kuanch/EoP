# Push Notifications (ntfy)

EoP uses a self-hosted [ntfy](https://ntfy.sh) server for real-time push notifications to mobile devices.

## Architecture

```
EoP App → notifier.py → HTTP POST → ntfy (Docker, port 8090) → ntfy.sh relay → Apple APNS → iPhone
```

## Setup

### 1. Start ntfy server

```bash
docker compose -f docker-compose.ntfy.yml up -d
```

### 2. Configure .env

```
NTFY_URL=http://localhost:8090
NTFY_TOPIC=eop-alerts
```

### 3. iOS Setup

1. Install ntfy app from App Store
2. Add subscription: `https://ntfy.kuanchlee.com/eop-alerts`
3. Set server to `https://ntfy.kuanchlee.com`

### 4. iOS Instant Push

Self-hosted ntfy requires an upstream relay for instant iOS push (otherwise polls every ~15 min).

Create `data/ntfy/server.yml`:
```yaml
base-url: https://ntfy.kuanchlee.com
upstream-base-url: https://ntfy.sh
```

This is mounted into the Docker container via `docker-compose.ntfy.yml`. The relay is free and forwards push triggers through Apple's APNS via ntfy.sh's gateway.

## Notification Format

Notifications are sent by the threat engine when items exceed the notify threshold:

- **Title**: `[LLM] Threat [news]: 8/10` or `[Rule] Threat [news]: 7/10`
  - `[LLM]` = scored by Claude Haiku LLM
  - `[Rule]` = scored by keyword rules only (LLM disabled or below threshold)
- **Body**: Article title + LLM rationale (in Traditional Chinese when LLM enabled)
- **Priority**: `urgent` (score ≥ 9) or `high` (score ≥ notify threshold)
- **Cooldown**: Per-topic, configurable (default 15 minutes)

## Configuration

All notification settings are configurable from the **Threats** tab in the dashboard:

| Setting | Default | Description |
|---------|---------|-------------|
| Notify Threshold | 7 | Final score needed to trigger notification |
| Cooldown | 15 min | Minimum time between notifications for same topic |
| LLM Enabled | true | Whether to use Claude Haiku for second-pass scoring |
| LLM Threshold | 5 | Rule score needed to trigger LLM assessment |
| Sources | news, pizzint | Which sources feed into threat detection |

## Testing

```bash
# Send a test notification
curl -H "Title: Test from EoP" -d "Hello!" http://localhost:8090/eop-alerts
```

## Cost

- **ntfy server**: Free (self-hosted, Docker)
- **ntfy.sh relay**: Free (250 msgs/day)
- **Claude Haiku**: ~$0.25/MTok output — negligible for threat rationale
- **Cloudflare tunnel** for ntfy: Free (unlimited bandwidth)
