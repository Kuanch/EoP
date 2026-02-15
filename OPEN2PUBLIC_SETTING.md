# Opening EoP Dashboard to Public Access

## Current Setup

- **Domain**: kuanchlee.com
- **Tunnel**: `fastapi-login` (UUID: `de67ab45-09e6-4b41-a565-18020df1e878`)
- **Config**: `/root/.cloudflared/config.yml`
- **App**: FastAPI on `localhost:8000`

## How to Start

### 1. Start the app

```bash
cd /home/sixigma/EoP
nohup venv/bin/python main.py &
```

### 2. Start the Cloudflare tunnel

```bash
nohup cloudflared tunnel run fastapi-login > /tmp/cloudflared.log 2>&1 &
```

### 3. Verify

```bash
# Check app responds
curl -s -o /dev/null -w "%{http_code}" http://localhost:8000
# Should return 302

# Check tunnel has active connections
cloudflared tunnel info fastapi-login
# Should show 4 connections (hkg/tpe regions)
```

Site is live at **https://kuanchlee.com**

## Troubleshooting

### Error 1033 (Argo Tunnel error)

Tunnel process exists but has no active connections. Fix:

```bash
pkill -f "cloudflared"
sleep 2
nohup cloudflared tunnel run fastapi-login > /tmp/cloudflared.log 2>&1 &
```

Check logs: `tail -20 /tmp/cloudflared.log`

### 502 Bad Gateway

App not running. Start it:

```bash
cd /home/sixigma/EoP
nohup venv/bin/python main.py &
```

### Check tunnel logs

```bash
tail -f /tmp/cloudflared.log
```

## Config Reference

`/root/.cloudflared/config.yml`:

```yaml
tunnel: de67ab45-09e6-4b41-a565-18020df1e878
credentials-file: /root/.cloudflared/de67ab45-09e6-4b41-a565-18020df1e878.json

ingress:
  - hostname: KUANCHLEE.COM
    service: http://localhost:8000
  - service: http_status:404
```

## Optional: Auto-start with systemd

```bash
sudo cp /home/sixigma/EoP/cloudflared.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable cloudflared
sudo systemctl start cloudflared
```
