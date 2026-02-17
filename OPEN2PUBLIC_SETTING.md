# Opening EoP Dashboard to Public Access

## Current Setup

- **Domain**: kuanchlee.com
- **Tunnel**: `eop-tunnel` (UUID: `de67ab45-09e6-4b41-a565-18020df1e878`)
- **Config**: `/root/.cloudflared/config.yml`
- **App**: FastAPI on `localhost:8000`
- **ntfy**: Push notifications on `localhost:8090` (exposed at `ntfy.kuanchlee.com`)

## Services

EoP runs as three systemd/Docker services:

| Service | Type | Command |
|---------|------|---------|
| `eop` | systemd | `systemctl start eop` |
| `cloudflared` | systemd | `systemctl start cloudflared` |
| `eop-ntfy` | Docker | `docker compose -f docker-compose.ntfy.yml up -d` |

### Start everything

```bash
sudo systemctl start eop cloudflared
cd /home/sixigma/EoP && docker compose -f docker-compose.ntfy.yml up -d
```

### Stop everything

```bash
sudo systemctl stop eop cloudflared
cd /home/sixigma/EoP && docker compose -f docker-compose.ntfy.yml down
```

### Check status

```bash
systemctl status eop cloudflared
docker ps | grep ntfy
curl -s -o /dev/null -w "%{http_code}" http://localhost:8000  # Should return 302
```

## Watchdog

A cron job runs every minute (`/home/sixigma/EoP/watchdog.sh`):
- Checks systemd services: `eop`, `cloudflared`
- Checks Docker container: `eop-ntfy`
- Verifies HTTP response from EoP
- Auto-restarts any failed service
- Log: `/tmp/eop-watchdog.log`

## Troubleshooting

### Error 1033 (Argo Tunnel error)

Tunnel process has no active connections:

```bash
sudo systemctl restart cloudflared
journalctl -u cloudflared --since "5 min ago"
```

### 502 Bad Gateway

App not running:

```bash
sudo systemctl restart eop
journalctl -u eop --since "5 min ago"
```

### Session keeps dropping

Cookie `samesite` must be `lax` (not `strict`) when behind Cloudflare proxy. This is already configured in `main.py`.

## Config Reference

`/root/.cloudflared/config.yml`:

```yaml
tunnel: de67ab45-09e6-4b41-a565-18020df1e878
credentials-file: /root/.cloudflared/de67ab45-09e6-4b41-a565-18020df1e878.json

ingress:
  # ntfy push notifications
  - hostname: ntfy.kuanchlee.com
    service: http://localhost:8090

  # Route your domain to local application
  - hostname: KUANCHLEE.COM
    service: http://localhost:8000

  # Catch-all rule (required)
  - service: http_status:404
```

**Note**: The hostname `KUANCHLEE.COM` must match the DNS CNAME exactly. Do not change the case.

Site is live at **https://kuanchlee.com**
