# Eye of Providence (EoP)

A real-time world monitoring dashboard built with FastAPI. Aggregates news, financial markets, military activity, and cyber threats into a unified dark-themed interface with live WebSocket updates and a geographic threat map.

## Modules

- **News** — RSS feeds from BBC World, Al Jazeera, CNA (World + Mainland), CBS World. Geo-tagged, threat-scored, deduplicated.
- **Markets** — Forex (EUR/USD, GBP/USD, USD/JPY), stocks (SPY, QQQ, DIA) via Polygon.io, crypto (BTC, ETH) via CoinGecko. TradingView-style intraday charts with CLOSED detection.
- **Military** — Aircraft tracking via OpenSky Network across 5 regions (Taiwan Strait, East Ukraine, Middle East, Korean Peninsula, South China Sea). Pentagon Pizza Index (pizzint.watch) and Polymarket geopolitical prediction odds.
- **Cyber** — CISA Known Exploited Vulnerabilities, Abuse.ch Feodo botnet C2 blocklist, AlienVault OTX threat pulses. Severity-sorted with IOC counts.
- **Map** — Leaflet map with dark CARTO tiles, news heatmap layer, military asset markers, and color-coded regional threat overlays scored 0-100.

## Quick Start

```bash
# 1. Create and activate virtual environment
python3 -m venv venv
source venv/bin/activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Initialize database and create user
python manage_users.py init
python manage_users.py create admin

# 4. Set API keys (optional, enhances data coverage)
export POLYGON_API_KEY="your_key"      # polygon.io - forex/stocks
export OTX_API_KEY="your_key"          # alienvault OTX - cyber threats

# 5. Run
python main.py
```

Open http://localhost:8000 and log in.

## Docker

```bash
docker-compose up -d
docker exec -it fastapi-login-app python manage_users.py init
docker exec -it fastapi-login-app python manage_users.py create admin
```

## Environment Variables

| Variable | Required | Purpose |
|----------|----------|---------|
| `POLYGON_API_KEY` | No | Polygon.io forex/stock data |
| `OTX_API_KEY` | No | AlienVault OTX cyber threat pulses |
| `OPENSKY_USERNAME` | No | OpenSky Network (higher rate limits) |
| `OPENSKY_PASSWORD` | No | OpenSky Network password |

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
  ├── database.py          SQLAlchemy models (User, Article, ThreatEvent)
  └── collectors/
      ├── base.py           Abstract async collector
      ├── news.py           RSS feeds
      ├── markets.py        Polygon.io + CoinGecko
      ├── military.py       OpenSky Network
      ├── cyber.py          CISA KEV + Abuse.ch + OTX
      ├── pizzint.py        Pentagon Pizza Index
      └── polymarket.py     Prediction market odds
```

## Security

- Session-based auth with bcrypt password hashing
- CSRF protection, rate limiting, secure cookies
- HTTPS via Cloudflare Tunnel (optional)

See `SECURITY.md` and `USER_MANAGEMENT.md` for details.
