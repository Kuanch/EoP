# Cloudflare Tunnel Setup Guide

This guide walks you through setting up Cloudflare Tunnel to expose your FastAPI application securely with HTTPS.

## Prerequisites

- ✅ Cloudflared installed (already done)
- ✅ Cloudflare account (free tier works)
- ⏳ A domain name (or use Cloudflare's free subdomain)

## Why Cloudflare Tunnel?

- **Free TLS certificate** - Auto-renewed, no configuration needed
- **Bypasses CGNAT** - Works without public IP or port forwarding
- **DDoS protection** - Cloudflare's network protects your application
- **Zero-config** - No firewall rules or router configuration needed
- **Access control** - Optional: Restrict who can access your app

---

## Setup Steps

### Step 1: Authenticate with Cloudflare

```bash
cloudflared tunnel login
```

This will:
1. Open your browser
2. Ask you to log in to Cloudflare
3. Select the domain you want to use
4. Download a certificate to `~/.cloudflared/cert.pem`

### Step 2: Create a Tunnel

```bash
cloudflared tunnel create fastapi-login
```

This creates:
- A tunnel with UUID (e.g., `a1b2c3d4-...`)
- Credentials file at `~/.cloudflared/<UUID>.json`

**Important**: Save the UUID - you'll need it for configuration!

### Step 3: Configure the Tunnel

Create `/root/.cloudflared/config.yml`:

```yaml
tunnel: <YOUR-TUNNEL-UUID>
credentials-file: /root/.cloudflared/<YOUR-TUNNEL-UUID>.json

ingress:
  # Route your domain to local application
  - hostname: yourapp.yourdomain.com
    service: http://localhost:8000

  # Catch-all rule (required)
  - service: http_status:404
```

**Replace**:
- `<YOUR-TUNNEL-UUID>` with your actual tunnel UUID
- `yourapp.yourdomain.com` with your domain/subdomain

### Step 4: Route DNS

Tell Cloudflare to route your domain to the tunnel:

```bash
cloudflared tunnel route dns fastapi-login yourapp.yourdomain.com
```

This automatically creates a CNAME record in your Cloudflare DNS.

### Step 5: Start the Tunnel

```bash
cloudflared tunnel run fastapi-login
```

Your app is now live at: **https://yourapp.yourdomain.com** 🎉

---

## Production Setup: Systemd Service

To keep the tunnel running permanently:

### Create systemd service file:

```bash
sudo nano /etc/systemd/system/cloudflared.service
```

```ini
[Unit]
Description=Cloudflare Tunnel
After=network.target

[Service]
Type=simple
User=root
ExecStart=/usr/local/bin/cloudflared tunnel run fastapi-login
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

### Enable and start the service:

```bash
sudo systemctl daemon-reload
sudo systemctl enable cloudflared
sudo systemctl start cloudflared
sudo systemctl status cloudflared
```

### Manage the service:

```bash
# Check status
sudo systemctl status cloudflared

# View logs
sudo journalctl -u cloudflared -f

# Restart
sudo systemctl restart cloudflared

# Stop
sudo systemctl stop cloudflared
```

---

## Quick Start (Development Mode)

For testing, you can use Quick Tunnel (no account needed):

```bash
cloudflared tunnel --url http://localhost:8000
```

This gives you a temporary URL like: `https://random-subdomain.trycloudflare.com`

**Note**: This URL changes every time and is for testing only!

---

## Application Updates for HTTPS

### 1. Update Cookie Security

In `main.py`, update cookie settings to use `secure=True`:

```python
response.set_cookie(
    key="session_token",
    value=session_token,
    httponly=True,
    secure=True,        # ← Now safe with HTTPS!
    samesite="strict",  # ← Stronger CSRF protection
    max_age=3600
)
```

### 2. Add Security Headers

Add HSTS (HTTP Strict Transport Security) header:

```python
@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)

    # Force HTTPS for future requests
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"

    return response
```

### 3. Trust Cloudflare's IP Forwarding

When behind Cloudflare, get real client IP:

```python
def get_client_ip(request: Request) -> str:
    """Get real client IP (works behind Cloudflare)"""
    # Cloudflare sets CF-Connecting-IP header
    cf_ip = request.headers.get("CF-Connecting-IP")
    if cf_ip:
        return cf_ip

    # Fallback to X-Forwarded-For
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()

    # Fallback to direct connection
    return request.client.host if request.client else "unknown"
```

---

## Troubleshooting

### Issue: "tunnel login" doesn't open browser

**Solution**: Manually visit the URL shown in terminal and paste the code.

### Issue: DNS not resolving

**Solution**: Wait 1-2 minutes for DNS propagation, or check:
```bash
cloudflared tunnel route ip show fastapi-login
```

### Issue: 502 Bad Gateway

**Possible causes**:
1. FastAPI app not running (`python main.py`)
2. Wrong port in config.yml (should match your app)
3. Firewall blocking localhost connections

**Check**:
```bash
# Test local app
curl http://localhost:8000

# Check tunnel status
cloudflared tunnel info fastapi-login
```

### Issue: Connection refused

**Solution**: Make sure your app listens on `0.0.0.0` not `127.0.0.1`:
```python
uvicorn.run(app, host="0.0.0.0", port=8000)  # ✅ Good
uvicorn.run(app, host="127.0.0.1", port=8000)  # ❌ Won't work with tunnel
```

---

## Security Considerations

### ✅ What Cloudflare Tunnel Provides:

- TLS/HTTPS encryption (protects data in transit)
- DDoS protection
- Web Application Firewall (WAF) - optional
- Rate limiting - optional
- Access control - optional (Cloudflare Access)

### ⚠️ What You Still Need:

Your application security features are still critical:
- ✅ Password hashing
- ✅ CSRF protection
- ✅ Rate limiting (application level)
- ⏳ Other security features (session management, etc.)

**Cloudflare Tunnel handles transport security**, but application security is your responsibility!

---

## Alternative: Quick Testing Without Domain

For development/testing without a domain:

```bash
# Terminal 1: Start your app
python main.py

# Terminal 2: Start tunnel (generates temporary URL)
cloudflared tunnel --url http://localhost:8000
```

Look for output like:
```
Your quick Tunnel has been created! Visit it at:
https://random-words-1234.trycloudflare.com
```

---

## Cost

**Free Tier Includes**:
- Unlimited tunnels
- Unlimited bandwidth
- Basic DDoS protection
- SSL certificates

**No credit card required!**

---

## Useful Commands

```bash
# List all tunnels
cloudflared tunnel list

# Show tunnel info
cloudflared tunnel info fastapi-login

# Delete a tunnel
cloudflared tunnel delete fastapi-login

# View tunnel logs
cloudflared tunnel run fastapi-login --loglevel debug

# Test connectivity
cloudflared tunnel run --url http://localhost:8000
```

---

## Next Steps

After setup:
1. Test your HTTPS connection
2. Update application to use `secure=True` for cookies
3. Add HSTS header
4. Set up systemd service for auto-start
5. Configure Cloudflare WAF rules (optional)
6. Set up Cloudflare Access for authentication (optional)

---

*For more information, visit: https://developers.cloudflare.com/cloudflare-one/connections/connect-apps/*
