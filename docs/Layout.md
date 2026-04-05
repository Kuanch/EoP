# Project Layout

## Directory Structure

```
EoP/
├── main.py                     # FastAPI app: routes, auth, WebSocket, background tasks
├── database.py                 # SQLAlchemy models and DB initialization
├── config.py                   # Centralized config: intervals, API keys, regions, feeds
├── ws_manager.py               # WebSocket connection manager (broadcast to all clients)
├── scoring.py                  # Regional threat scoring algorithm (0-100)
├── threat_engine.py            # Hybrid threat detection: keyword rules + Claude Haiku LLM
├── cyber_escalation.py         # Cyber escalation pipeline (IODA signal correlation)
├── notifier.py                 # Push notifications via ntfy
├── manage_users.py             # CLI user management (create, delete, password, etc.)
├── threat_rules.json           # Threat config: keyword weights, thresholds, LLM prompt
├── opensky_credentials.json    # OpenSky OAuth2 credentials (not in git)
├── requirements.txt            # Python dependencies
│
├── collectors/                 # Data source collectors (most inherit BaseCollector)
│   ├── base.py                 #   Abstract base: run loop, error handling, interval
│   ├── news.py                 #   RSS feeds (BBC, Al Jazeera, CNA, CBS) — 5min
│   ├── markets.py              #   Finnhub stocks, Polygon forex, CoinGecko crypto — 1min
│   ├── military.py             #   OpenSky Network aircraft tracking (OAuth2) — 5min poll, 5s broadcast
│   ├── cyber.py                #   CISA KEV, Abuse.ch Feodo, AlienVault OTX — 30min
│   ├── ships.py                #   AIS ship tracking (Taiwan MPB + AISstream WS) — 5s broadcast
│   ├── pizzint.py              #   Pentagon Pizza Index (OPTEMPO levels) — 5min
│   └── polymarket.py           #   Geopolitical prediction market odds — 5min
│
├── static/
│   ├── js/
│   │   ├── ws.js               #   WebSocket client with auto-reconnect
│   │   ├── dashboard.js        #   Tab switching, hash navigation, utilities
│   │   ├── news.js             #   News feed rendering, source filtering
│   │   ├── markets.js          #   Market tables, Chart.js intraday charts
│   │   ├── military.js         #   Aircraft listing and details
│   │   ├── cyber.js            #   Cyber events, stats cards, alerts toggle
│   │   ├── map.js              #   Leaflet map: markers, heatmap, regional overlays, filters
│   │   └── threats.js          #   Threat feed display, config editor (keywords, LLM, thresholds)
│   └── css/
│       └── dashboard.css       #   Dark theme, cards, layout, responsive grid, animations
│
├── templates/
│   ├── base.html               #   HTML base template
│   ├── login.html              #   Login page with CSRF protection
│   ├── dashboard.html          #   Main app: tab navigation, content containers
│   └── index.html              #   Alternative dashboard entry point
│
├── data/
│   ├── users.db                #   SQLite database (users, articles, sessions, threats)
│   ├── stock_intraday.json     #   Persistent stock intraday price data
│   └── ntfy/                   #   ntfy server data (Docker volume)
│
├── logs/
│   └── security.log            #   Security event logging (attacks, brute force, etc.)
│
├── docs/                       #   Documentation
│   ├── Layout.md               #   This file
│   ├── API.md                  #   REST & WebSocket API reference
│   └── plans/                  #   Implementation plans and design docs
│
├── CLAUDE.md                   #   Claude Code project context (deployment, architecture)
├── Dockerfile                  #   Docker image definition (Python 3.12, non-root appuser)
├── docker-compose.yml          #   App + Cloudflare tunnel containers
├── docker-compose.ntfy.yml     #   ntfy push notification server
├── cloudflared.service         #   Cloudflare Tunnel systemd unit (legacy, now Docker-based)
└── watchdog.sh                 #   Process watchdog script
```

## Core Modules

### main.py — Application Entry Point

FastAPI application with:
- **Authentication**: Session-based with bcrypt passwords, CSRF tokens, brute-force lockout
- **Routes**: HTML pages (login, dashboard) + REST API endpoints + WebSocket
- **Background tasks**: Launches all collectors on startup
- **Security middleware**: Rate limiting, security headers, attack pattern detection
- **WebSocket**: Origin validation, session auth, real-time broadcast to all clients

### database.py — Data Models

Four SQLAlchemy models backed by SQLite (`data/users.db`):

| Model | Purpose | Key Fields |
|-------|---------|------------|
| `User` | Authentication | username, password_hash (bcrypt), is_active, last_login |
| `Article` | News persistence | url_hash (dedup key), title, summary, source, geo coords, threat_score |
| `SessionToken` | Session auth | token (64-char), username, created_at (24h expiry) |
| `ThreatEvent` | Cyber event log | event_type, title, severity, source, ioc_count |

### config.py — Centralized Configuration

All polling intervals, API keys, feed URLs, monitored regions, and geo-tagging keywords. API keys are read from environment variables with empty string defaults (all optional).

### Environment Variables

| Variable | Purpose |
|----------|---------|
| `POLYGON_API_KEY` | Polygon.io forex/stock data |
| `FINNHUB_API_KEY` | Finnhub real-time US stock quotes |
| `OTX_API_KEY` | AlienVault OTX cyber threat pulses |
| `ANTHROPIC_API_KEY` | Claude Haiku LLM threat classification |
| `AISSTREAM_API_KEY` | AISstream live ship tracking WebSocket |
| `OPENSKY_CLIENT_ID` | OpenSky Network OAuth2 (alternative to credentials file) |
| `OPENSKY_CLIENT_SECRET` | OpenSky Network OAuth2 secret |
| `NTFY_URL` | ntfy server URL (default: `http://localhost:8090`) |
| `NTFY_TOPIC` | ntfy topic name (default: `eop-alerts`) |
| `ALLOWED_ORIGINS` | Comma-separated WebSocket origin allowlist |
| `SECRET_KEY` | CSRF token signing key (auto-generated and appended to `.env` if missing) |
| `ENVIRONMENT` | Set to `production` to enable Secure cookie flag |

### ws_manager.py — WebSocket Manager

`ConnectionManager` class: connect, disconnect, broadcast. Messages are JSON with `{module, data}` format. Dead connections are cleaned up automatically during broadcast.

### scoring.py — Regional Threat Scoring

Computes 0-100 threat scores per monitored region using:
- News keyword weight (max 50 points)
- News article count (max 20 points)
- Military asset presence (max 20 points)
- Cyber event severity (max 10 points)

### threat_engine.py — Hybrid Threat Detection

Two-pass pipeline:
1. **Rule-based**: Score text against keyword weights from `threat_rules.json`
2. **LLM classification**: Items above `llm_threshold` sent to Claude Haiku for severity, threat type, and rationale (Traditional Chinese)

Maintains a rolling feed (500 items) and daily stats. Triggers ntfy notifications when `final_score >= notify_threshold`.

### notifier.py — Push Notifications

Sends alerts to ntfy server with title, message, priority, and emoji tags. Per-key cooldown prevents notification spam (default 15 min).

## Collectors

Most collectors inherit `BaseCollector` which provides:
- `async run()` — Main loop: collect, handle errors, sleep for interval
- `async collect()` — Abstract method, implemented by each collector
- `stop()` — Graceful shutdown via `_running` flag

Exception: `ShipCollector` does **not** inherit `BaseCollector`. It manages its own dual-source lifecycle (Taiwan MPB polling + AISstream WebSocket) with a separate broadcast loop.

Each collector broadcasts data via `ws_manager.broadcast(module, data)`.

| Collector | Module | Poll Interval | Broadcast Interval | Data Source |
|-----------|--------|---------------|-------------------|-------------|
| NewsCollector | `news` | 300s | On collect | RSS feeds (5 sources) |
| MarketsCollector | `markets` | 60s | On collect | Finnhub, Polygon, CoinGecko |
| MilitaryCollector | `military` | 300s | 5s (cached) | OpenSky Network (OAuth2) |
| CyberCollector | `cyber` | 1800s | On collect | CISA, Abuse.ch, OTX |
| ShipCollector | `ships` | 60s (MPB) | 5s (batched) | Taiwan MPB + AISstream |
| PizzIntCollector | `pizzint` | 300s | On collect | pizzint.watch |
| PolymarketCollector | `polymarket` | 300s | On collect | Polymarket API |

## Frontend Architecture

Vanilla JavaScript (no framework) with Leaflet for maps and Chart.js for charts. All modules follow the same pattern:
1. Fetch initial data from REST API on tab activation
2. Listen for WebSocket updates for real-time data
3. Render into tab-specific containers

The map module uses incremental marker updates (keyed by icao24/mmsi) with `requestAnimationFrame` animation for smooth position transitions.

## Security

- **Session auth**: DB-backed tokens, 24h expiry, secure cookies
- **CSRF**: `URLSafeTimedSerializer` tokens on all state-changing forms
- **Rate limiting**: Per-IP via slowapi (10/min login, 60/min API)
- **Brute force**: 5 failed attempts → 1h IP lockout
- **Headers**: HSTS, X-Frame-Options DENY, CSP (self + unpkg.com)
- **WebSocket**: Origin header validation against allowlist
- **Attack detection**: Regex patterns for SQLi, XSS, path traversal
- **Static asset auth**: `/static/js/` and `/static/css/` return 401 if not logged in (middleware)
- **Logging**: Dedicated `logs/security.log`
