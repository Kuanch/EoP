# EoP Quick Setup Guide

Quick reference for starting all EoP services. For full documentation see `README.md`.

## Architecture

```
Internet → Cloudflare Tunnel → localhost:8000 (EoP FastAPI)
                              → localhost:8090 (ntfy push server)
```

| Service | Port | Manager | Config |
|---------|------|---------|--------|
| EoP app | 8000 | systemd (`eop.service`) | `.env` + `config.py` |
| ntfy | 8090 | Docker (`eop-ntfy`) | `data/ntfy/server.yml` |
| Cloudflare tunnel | — | systemd (`cloudflared.service`) | `/root/.cloudflared/config.yml` |

## 1. Start All Services

```bash
cd /home/sixigma/EoP

# EoP server
sudo systemctl start eop

# ntfy push notifications
docker compose -f docker-compose.ntfy.yml up -d

# Cloudflare tunnel (HTTPS access via kuanchlee.com)
sudo systemctl start cloudflared
```

## 2. Verify Everything Is Running

```bash
# Check service status
sudo systemctl status eop --no-pager -l
sudo systemctl status cloudflared --no-pager -l
docker ps --filter name=eop-ntfy

# Health checks (local)
curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/login   # expect 200
curl -s -o /dev/null -w "%{http_code}" http://localhost:8090/v1/health  # expect 200

# Health checks (via tunnel — CRITICAL for iOS push to work)
curl -s -o /dev/null -w "%{http_code}" https://kuanchlee.com/login          # expect 200
curl -s -o /dev/null -w "%{http_code}" https://ntfy.kuanchlee.com/v1/health # expect 200

# Test ntfy push
curl -H "Title: Test" -d "EoP startup OK" http://localhost:8090/eop-alerts
```

## 3. Stop All Services

```bash
sudo systemctl stop eop
sudo systemctl stop cloudflared
docker compose -f docker-compose.ntfy.yml down
```

## 4. View Logs

```bash
# EoP application logs (live)
journalctl -u eop -f

# Cloudflare tunnel logs
journalctl -u cloudflared -f

# ntfy logs
docker logs -f eop-ntfy

# Security events
tail -f /home/sixigma/EoP/logs/security.log
```

## 5. Watchdog (Auto-Restart)

A cron job monitors all 3 services and restarts any that go down:

```bash
# Enable (runs every minute)
crontab -e
# Add: * * * * * /home/sixigma/EoP/watchdog.sh >> /tmp/eop-watchdog.log 2>&1

# Check watchdog output
tail -f /tmp/eop-watchdog.log
```

## 6. User Management

```bash
cd /home/sixigma/EoP

# List users
venv/bin/python manage_users.py list

# Create user (interactive password prompt)
venv/bin/python manage_users.py create <username>

# Reset password
venv/bin/python manage_users.py password <username>

# Deactivate/activate
venv/bin/python manage_users.py deactivate <username>
venv/bin/python manage_users.py activate <username>
```

## 7. Key File Locations

| File | Purpose |
|------|---------|
| `/home/sixigma/EoP/.env` | API keys, secrets, ntfy config |
| `/home/sixigma/EoP/config.py` | Polling intervals, regions, feeds |
| `/home/sixigma/EoP/threat_rules.json` | Threat scoring keywords + thresholds |
| `/home/sixigma/EoP/data/users.db` | SQLite database (users, sessions, articles) |
| `/home/sixigma/EoP/data/ntfy/server.yml` | ntfy upstream relay config |
| `/root/.cloudflared/config.yml` | Tunnel routes (kuanchlee.com → localhost) |
| `/etc/systemd/system/eop.service` | EoP systemd unit |
| `/etc/systemd/system/cloudflared.service` | Tunnel systemd unit |

## 8. Systemd Service Details

**eop.service** — runs as `sixigma`, auto-restarts on crash:
```
ExecStart=/home/sixigma/EoP/venv/bin/python /home/sixigma/EoP/main.py
WorkingDirectory=/home/sixigma/EoP
EnvironmentFile=/home/sixigma/EoP/.env
```

**cloudflared.service** — runs as `root`:
```
ExecStart=/usr/local/bin/cloudflared tunnel run eop-tunnel
```

After editing either service file: `sudo systemctl daemon-reload`

## 9. Cloudflare Tunnel

Tunnel config at `/root/.cloudflared/config.yml`:
```yaml
tunnel: ccaf629b-f4f1-47f6-bd3b-3e9ee600ba73
credentials-file: /root/.cloudflared/ccaf629b-f4f1-47f6-bd3b-3e9ee600ba73.json

ingress:
  - hostname: kuanchlee.com
    service: http://localhost:8000
  - hostname: ntfy.kuanchlee.com
    service: http://localhost:8090
  - service: http_status:404
```

Useful commands:
```bash
# List tunnels
cloudflared tunnel list

# Get tunnel token (if re-deploying)
cloudflared tunnel token eop-tunnel

# Route DNS (one-time, already done)
cloudflared tunnel route dns eop-tunnel kuanchlee.com
cloudflared tunnel route dns eop-tunnel ntfy.kuanchlee.com
```

## 10. Troubleshooting

| Symptom | Check | Fix |
|---------|-------|-----|
| Can't reach kuanchlee.com | `systemctl status cloudflared` | `sudo systemctl restart cloudflared` |
| Login page won't load | `curl localhost:8000/login` | `sudo systemctl restart eop` |
| No push notifications | `docker ps \| grep ntfy` | `docker compose -f docker-compose.ntfy.yml up -d` |
| **Empty push on iOS** | `curl -s -o /dev/null -w "%{http_code}" https://ntfy.kuanchlee.com/v1/health` | Tunnel is down — iOS gets APNS ping but can't fetch message body. Fix: `sudo systemctl restart cloudflared` |
| Stale data / health dots red | `journalctl -u eop -n 50` | Check API keys in `.env`, restart eop |
| Session drops after 2min | Cookie issue behind Cloudflare | Verify `samesite="lax"` in main.py |
| OpenSky 429 errors | Rate limited | Reduce `MILITARY_POLL_INTERVAL` in config.py |
