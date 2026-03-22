# Eye of Providence (EoP)

A real-time world monitoring dashboard built with FastAPI. Aggregates news, financial markets, military activity, and cyber threats into a unified dark-themed interface with live WebSocket updates and a geographic threat map.

## Modules

- **News** — RSS feeds from BBC World, Al Jazeera, CNA (World + Mainland), CBS World. Geo-tagged, threat-scored, deduplicated. Articles older than 6 hours are filtered out.
- **Markets** — Forex (EUR/USD, USD/JPY), stocks (SPY, QQQ) via Polygon.io, crypto (BTC, ETH) via CoinGecko. TradingView-style intraday charts with market open/closed detection. Fear & Greed index.
- **Military** — Aircraft tracking via OpenSky Network across 5 regions (Taiwan Strait, East Ukraine, Middle East, Korean Peninsula, South China Sea). Pentagon Pizza Index (pizzint.watch) and Polymarket geopolitical prediction odds.
- **Cyber** — CISA Known Exploited Vulnerabilities, Abuse.ch Feodo botnet C2 blocklist, AlienVault OTX threat pulses. Severity-sorted with IOC counts. Alerts toggle on/off.
- **Map** — Leaflet map with dark CARTO tiles, news heatmap layer, military asset markers, AIS ship tracking (AISstream + Taiwan MPB), and color-coded regional threat overlays scored 0-100. Ship filtering by flag, type, and speed.
- **Threats** — Hybrid threat detection with configurable keyword rules + Claude Haiku LLM classification. Two-pass pipeline: rule-based scoring filters items, then LLM assesses severity with rationale in Traditional Chinese. Dashboard config panel for thresholds, keyword editor, LLM prompt, and source toggles.

## Push Notifications

Self-hosted [ntfy](https://ntfy.sh) server for real-time push notifications to mobile devices.

- Threat alerts tagged `[LLM]` (LLM-assessed) or `[Rule]` (keyword-only)
- Per-topic cooldown to prevent notification spam
- iOS instant push via ntfy.sh upstream APNS relay
- Configurable notify threshold and cooldown in the Threats tab

```bash
# Start ntfy server
docker compose -f docker-compose.ntfy.yml up -d
```

Configure in `.env`:
```
NTFY_URL=http://localhost:8090
NTFY_TOPIC=eop-alerts
```

For **iOS push notifications**, ntfy must relay through ntfy.sh upstream (APNS). Create `data/ntfy/server.yml`:
```yaml
base-url: "https://your-ntfy-domain.com"
upstream-base-url: "https://ntfy.sh"
```

Restart ntfy after changing the config: `docker restart eop-ntfy`

## Quick Start

```bash
# 1. Install system dependencies (Debian/Ubuntu)
# python3-venv is required but not always installed by default
apt install python3.12-venv  # adjust version to match your python3

# 2. Create virtual environment
python3 -m venv venv

# 3. Install dependencies — always use the venv binary directly
# (do NOT use `source venv/bin/activate` + pip, it may resolve to system pip)
venv/bin/pip install -r requirements.txt

# 4. Create required directories
mkdir -p logs data

# 5. Initialize database and create user
# Database is stored at data/users.db (created automatically on init)
venv/bin/python3 manage_users.py init
venv/bin/python3 manage_users.py create admin

# 6. Set API keys in .env (optional, enhances data coverage)
# Copy .env.example to .env and fill in keys, or export them:
cp .env.example .env
export POLYGON_API_KEY="your_key"        # polygon.io - forex/stocks
export FINNHUB_API_KEY="your_key"        # finnhub.io - real-time forex/stocks
export OTX_API_KEY="your_key"            # alienvault OTX - cyber threats
export ANTHROPIC_API_KEY="your_key"      # anthropic - LLM threat assessment
export AISSTREAM_API_KEY="your_key"      # aisstream.io - live AIS ship data

# 7. Start ntfy (optional, for push notifications)
docker compose -f docker-compose.ntfy.yml up -d

# 8. Run — use venv python directly to avoid PATH issues
venv/bin/python3 main.py
```

Open http://localhost:8000 and log in.

> **Note:** If the `data/` directory and `data/users.db` already exist (e.g. cloning a production copy), skip step 3. The app will start with the existing database.

## Docker

```bash
docker-compose up -d
docker exec -it fastapi-login-app python manage_users.py init
docker exec -it fastapi-login-app python manage_users.py create admin
```

## Environment Variables

| Variable | Required | Purpose |
|----------|----------|---------|
| `POLYGON_API_KEY` | No | Polygon.io forex/stock data (free tier: 5 req/min) |
| `OTX_API_KEY` | No | AlienVault OTX cyber threat pulses |
| `ANTHROPIC_API_KEY` | No | Claude Haiku LLM threat classification |
| `AISSTREAM_API_KEY` | No | AISstream live ship tracking |
| `FINNHUB_API_KEY` | No | Finnhub real-time forex/stock quotes |
| `NTFY_URL` | No | ntfy server URL (default: http://localhost:8090) |
| `NTFY_TOPIC` | No | ntfy topic name (default: eop-alerts) |

OpenSky Network uses OAuth2 via `opensky_credentials.json` (not committed to git).

## Threat Detection

The hybrid threat engine (`threat_engine.py`) uses a two-pass pipeline:

1. **Rule-based scoring** — Configurable keyword weights in `threat_rules.json`. Fast first pass filters items.
2. **LLM classification** — Items scoring above the LLM threshold are sent to Claude Haiku for severity assessment, threat type classification, and rationale (in Traditional Chinese).

Notifications are sent via ntfy when the final score exceeds the notify threshold. All settings are editable from the Threats tab in the dashboard.

## Architecture

```
Browser (Vanilla JS + Leaflet CDN)
  ├── HTTPS ──> FastAPI (Jinja2, REST API)
  └── WSS ───> FastAPI WebSocket (/ws)

Backend
  ├── main.py              Routes, WS endpoint, background tasks
  ├── ws_manager.py        WebSocket connection manager
  ├── config.py            Feed URLs, API keys, intervals
  ├── scoring.py           Region threat scoring (0-100)
  ├── threat_engine.py     Hybrid threat detection (rules + LLM)
  ├── threat_rules.json    Configurable keyword rules and thresholds
  ├── notifier.py          Push notifications via ntfy
  ├── database.py          SQLAlchemy models (User, Article, ThreatEvent)
  └── collectors/
      ├── base.py           Abstract async collector
      ├── news.py           RSS feeds (6-hour freshness filter)
      ├── markets.py        Polygon.io + CoinGecko + Fear & Greed
      ├── military.py       OpenSky Network (5 regions)
      ├── cyber.py          CISA KEV + Abuse.ch + OTX
      ├── ships.py          AIS ship tracking (AISstream + Taiwan MPB)
      ├── pizzint.py        Pentagon Pizza Index
      └── polymarket.py     Prediction market odds
```

## Cloudflare Tunnel (Remote Access)

For HTTPS access from outside your local network, use [Cloudflare Tunnel](https://developers.cloudflare.com/cloudflare-one/connections/connect-apps/).

1. Install cloudflared:
```bash
curl -fsSL https://pkg.cloudflare.com/cloudflare-main.gpg | tee /usr/share/keyrings/cloudflare-main.gpg >/dev/null
echo "deb [signed-by=/usr/share/keyrings/cloudflare-main.gpg] https://pkg.cloudflare.com/cloudflared $(lsb_release -cs) main" \
  | tee /etc/apt/sources.list.d/cloudflared.list
apt update && apt install cloudflared
```

2. Authenticate and create a tunnel:
```bash
cloudflared tunnel login
cloudflared tunnel create fastapi-login
```

3. Configure `~/.cloudflared/config.yml`:
```yaml
tunnel: <TUNNEL_UUID>
credentials-file: /root/.cloudflared/<TUNNEL_UUID>.json

ingress:
  - hostname: ntfy.yourdomain.com
    service: http://localhost:8090
  - hostname: yourdomain.com
    service: http://localhost:8000
  - hostname: "*.yourdomain.com"
    service: http://localhost:8000
  - service: http_status:404
```

4. Add DNS routes and start:
```bash
cloudflared tunnel route dns fastapi-login yourdomain.com
cloudflared tunnel route dns fastapi-login ntfy.yourdomain.com
cloudflared tunnel --config ~/.cloudflared/config.yml run fastapi-login
```

A systemd service file (`cloudflared.service`) is included for running the tunnel as a daemon.

## Security

- Session-based auth with bcrypt password hashing
- CSRF protection, rate limiting, secure cookies
- HTTPS via Cloudflare Tunnel (optional)

See `SECURITY.md` and `USER_MANAGEMENT.md` for details.
