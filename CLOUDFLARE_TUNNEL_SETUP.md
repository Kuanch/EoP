# Cloudflare Tunnel Setup Guide

## Current Configuration

- **Tunnel name**: `eop-tunnel`
- **Tunnel UUID**: `de67ab45-09e6-4b41-a565-18020df1e878`
- **Config**: `/root/.cloudflared/config.yml`
- **Credentials**: `/root/.cloudflared/de67ab45-09e6-4b41-a565-18020df1e878.json`

### Hostnames

| Hostname | Service | Purpose |
|----------|---------|---------|
| `KUANCHLEE.COM` | `http://localhost:8000` | EoP dashboard |
| `ntfy.kuanchlee.com` | `http://localhost:8090` | ntfy push notifications |

## Why Cloudflare Tunnel?

- **Free TLS certificate** — auto-renewed, no configuration needed
- **Bypasses CGNAT** — works without public IP or port forwarding
- **DDoS protection** — Cloudflare's network protects your application
- **Zero-config** — no firewall rules or router configuration needed

---

## Setup Steps

### Step 1: Authenticate with Cloudflare

```bash
cloudflared tunnel login
```

### Step 2: Create a Tunnel

```bash
cloudflared tunnel create eop-tunnel
```

### Step 3: Configure the Tunnel

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

**Important**: The hostname `KUANCHLEE.COM` must match the DNS CNAME record exactly. Do not change the case — this broke access when changed to lowercase.

### Step 4: Route DNS

```bash
cloudflared tunnel route dns eop-tunnel KUANCHLEE.COM
cloudflared tunnel route dns eop-tunnel ntfy.kuanchlee.com
```

This creates CNAME records in Cloudflare DNS pointing to the tunnel.

---

## Production Setup: Systemd Service

The tunnel runs as a systemd service at `/etc/systemd/system/cloudflared.service`:

```ini
[Unit]
Description=Cloudflare Tunnel
After=network.target

[Service]
Type=simple
User=root
ExecStart=/usr/local/bin/cloudflared tunnel run eop-tunnel
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

### Manage the service

```bash
sudo systemctl start cloudflared
sudo systemctl stop cloudflared
sudo systemctl restart cloudflared
sudo systemctl status cloudflared
journalctl -u cloudflared -f
```

---

## Application HTTPS Settings

### Cookie Security

Behind Cloudflare proxy, cookies must use `samesite="lax"` (not `strict`), otherwise sessions drop after ~2 minutes:

```python
response.set_cookie(
    key="session_token",
    value=session_token,
    httponly=True,
    secure=True,
    samesite="lax",
    max_age=86400
)
```

### Real Client IP

Cloudflare sets `CF-Connecting-IP` header with the real client IP. The app uses this for rate limiting.

### Security Headers

All responses include HSTS, X-Frame-Options: DENY, X-Content-Type-Options: nosniff, and other security headers.

---

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
```

### DNS not resolving

Wait 1-2 minutes for propagation, or check:

```bash
cloudflared tunnel info eop-tunnel
```

---

## Useful Commands

```bash
cloudflared tunnel list
cloudflared tunnel info eop-tunnel
journalctl -u cloudflared --since "10 min ago"
```

---

## Cost

- **Cloudflare Tunnel**: Free (unlimited tunnels and bandwidth)
- **SSL certificates**: Free (auto-renewed)
- **DDoS protection**: Free (basic tier)
