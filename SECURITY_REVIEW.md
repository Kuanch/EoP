# Security Review - Eye of Providence

**Last Updated**: 2026-02-17
**Previous Review**: 2025-10-25

---

## Current Security Measures

### 1. Authentication & Session Management
- ✅ **Bcrypt password hashing** with salt (database.py)
- ✅ **DB-backed sessions** — sessions persist in SQLite across restarts (SessionToken table)
- ✅ **24-hour session expiry** with automatic cleanup
- ✅ **Secure cookies** — httponly, secure (in production), samesite=lax
- ✅ **POST-only logout** — prevents CSRF logout attacks

### 2. Rate Limiting & Attack Prevention
- ✅ **Login rate limiting**: 5 failed attempts per 15 minutes per IP
- ✅ **API rate limiting**: SlowAPI integration on all endpoints
- ✅ **Real IP detection** behind Cloudflare proxy (CF-Connecting-IP header)

### 3. CSRF Protection
- ✅ **Token-based CSRF protection** using URLSafeTimedSerializer on login form
- ✅ **1-hour token expiration** to limit replay attacks
- ✅ **POST-only logout** to prevent CSRF logout via `<img>` tags

### 4. Input Validation
- ✅ **Threat config validation** — POST /api/threats/config validates all keys, types, and ranges
  - Whitelist of allowed keys (keyword_rules, llm_threshold, etc.)
  - Keyword weights validated 0-10
  - Thresholds validated against min/max ranges
  - LLM prompt capped at 2000 characters
  - Boolean fields strictly validated

### 5. XSS Prevention
- ✅ **News cards** — event delegation instead of inline onclick (prevents single-quote injection)
- ✅ **DOM-based escaping** — `escapeHtml()` / `_esc()` in all JS rendering
- ✅ **Jinja2 auto-escaping** in templates
- ✅ **Security headers** — X-XSS-Protection, X-Content-Type-Options

### 6. Security Headers
All responses include:
- ✅ **HSTS**: Strict-Transport-Security with 1-year max-age
- ✅ **X-Content-Type-Options**: nosniff
- ✅ **X-Frame-Options**: DENY
- ✅ **X-XSS-Protection**: Enabled with block mode
- ✅ **Referrer-Policy**: strict-origin-when-cross-origin

### 7. HTTPS & Network Security
- ✅ **Cloudflare Tunnel**: All traffic encrypted via HTTPS
- ✅ **No direct port exposure**: App only accessible via tunnel
- ✅ **Systemd services**: Both EoP and cloudflared run as systemd services with auto-restart
- ✅ **Watchdog cron**: Checks all services every minute, restarts if down

### 8. Secrets Management
- ✅ `.env` file in `.gitignore` — never committed
- ✅ `data/` directory in `.gitignore` — database and ntfy config protected
- ✅ `opensky_credentials.json` in `.gitignore`
- ✅ API keys loaded from environment variables only

---

## Security Fixes (2026-02-17)

| Fix | Severity | Description |
|-----|----------|-------------|
| XSS in news cards | Critical | Replaced inline `onclick` with event delegation to prevent single-quote injection from RSS URLs |
| Config validation | Critical | Added strict schema validation on `POST /api/threats/config` — whitelist keys, validate types/ranges |
| CSRF logout | High | Changed `/logout` from GET to POST — prevents forced logout via `<img src="/logout">` |
| Persistent sessions | High | Moved sessions from in-memory dict to SQLite — logins survive server restarts |
| Cookie samesite | High | Changed from `strict` to `lax` — fixes session dropping through Cloudflare tunnel proxy |

---

## Known Limitations

| Issue | Severity | Notes |
|-------|----------|-------|
| No CSP header | Medium | Content-Security-Policy not set — inline scripts allowed |
| No SRI on CDN scripts | Medium | Leaflet loaded from unpkg.com without integrity hashes |
| IP header spoofing | Medium | CF-Connecting-IP trusted unconditionally when not behind Cloudflare |
| SQLite concurrency | Low | `check_same_thread=False` — fine for single worker |

---

## Environment Files Checklist

- ✅ `.env` — not committed (contains API keys, SECRET_KEY)
- ✅ `data/` — not committed (contains users.db, ntfy config)
- ✅ `opensky_credentials.json` — not committed
- ✅ `threat_rules.json` — committed (no secrets, user-configurable)

---

## Monitoring

### Watchdog
A cron job runs every minute (`/home/sixigma/EoP/watchdog.sh`):
- Checks systemd services: `eop`, `cloudflared`
- Checks Docker container: `eop-ntfy`
- Verifies HTTP response from EoP
- Restarts any failed service automatically

### Commands
```bash
# Service status
systemctl status eop
systemctl status cloudflared

# Recent logs
journalctl -u eop --since "10 min ago"
journalctl -u cloudflared --since "10 min ago"

# Watchdog log
tail -20 /tmp/eop-watchdog.log
```

---

**Next Review**: After any security incident or monthly
