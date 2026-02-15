# Eye of Providence - Implementation Plan

## Overview
Transform the existing EoP FastAPI login app into a real-time world monitoring dashboard with WebSocket-driven data from news, markets, military, and cyber sources.

## Architecture

```
Browser (Vanilla JS + Leaflet via CDN)
  ├── HTTPS → FastAPI (Jinja2 templates, REST API)
  └── WSS  → FastAPI WebSocket (/ws)

FastAPI Backend
  ├── main.py          (routes, WS endpoint, background task launcher)
  ├── ws_manager.py    (WebSocket connection manager)
  ├── config.py        (feed URLs, API keys, polling intervals)
  ├── scoring.py       (region threat scoring algorithm)
  ├── collectors/
  │   ├── base.py      (abstract async collector)
  │   ├── news.py      (RSS feeds: BBC, Al Jazeera, CNA)
  │   ├── markets.py   (Polygon.io forex+stocks, CoinGecko crypto, Fear&Greed)
  │   ├── military.py  (OpenSky aircraft tracking)
  │   └── cyber.py     (CISA KEV, Abuse.ch, AlienVault OTX)
  └── database.py      (User + Article + ThreatEvent models)
```

**Data flow**: Background asyncio tasks poll sources → normalize → score → cache/store → broadcast JSON via WebSocket → frontend JS updates DOM per module.

## Implementation Phases

### Phase 1: Core Infrastructure
- WebSocket server (ConnectionManager)
- Background task framework (BaseCollector)
- Centralized config (config.py)
- Dark-themed dashboard shell with 5-tab bar
- Tab switching, WebSocket client with auto-reconnect
- Protected /dashboard route, static file serving

### Phase 2: News Module
- RSS feed collector (BBC, Al Jazeera, CNA)
- Article normalization, deduplication, geo-tagging
- Article persistence in SQLite
- News tab UI with source filtering

### Phase 3: Markets Module
- **Primary monitors (large charts):** EUR/USD forex via Polygon.io + Bitcoin via CoinGecko
- **Secondary monitors (small charts):** GBP/USD, USD/JPY, Ethereum, S&P 500 (SPY), NASDAQ (QQQ), Dow Jones (DIA), Tesla (TSLA)
- TradingView-style 30-day canvas charts with prev close reference line, filled area, price axis, time axis
- Polygon.io free tier with rate-limit-aware staggered requests (13s between symbols)
- CoinGecko 30-day market_chart API for crypto historical data
- Scrolling ticker bar, Fear & Greed gauge

### Phase 4: Military Module
- OpenSky Network aircraft tracking across 5 monitored regions
- Region-filtered bounding boxes (Taiwan Strait, East Ukraine, Middle East, Korean Peninsula, South China Sea)
- Asset table with region summary cards

### Phase 5: Cyber Module
- CISA KEV, Abuse.ch Feodo, AlienVault OTX
- Severity-sorted threat cards with stats bar
- ThreatEvent persistence

### Phase 6: Geographic Map + Threat Scoring
- Leaflet map with dark CARTO tiles
- News heatmap layer (leaflet.heat), military markers
- Region threat scoring (keyword weights + volume + military + cyber → 0-100)
- Layer toggle controls

## Data Sources

| Module | Source | Ticker/URL | Poll Interval |
|--------|--------|------------|---------------|
| News | BBC World RSS | `https://feeds.bbci.co.uk/news/world/rss.xml` | 5 min |
| News | Al Jazeera RSS | `https://www.aljazeera.com/xml/rss/all.xml` | 5 min |
| News | Taiwan CNA RSS | `https://www.cna.com.tw/rss/aall.xml` | 5 min |
| Markets | Polygon.io Forex | `C:EURUSD`, `C:GBPUSD`, `C:USDJPY` | 60 sec |
| Markets | Polygon.io Stocks | `SPY`, `QQQ`, `DIA`, `TSLA` | 60 sec |
| Markets | CoinGecko | BTC, ETH | 60 sec |
| Markets | Fear & Greed | alternative.me | 15 min |
| Military | OpenSky Network | 5 regional bounding boxes | 120 sec |
| Cyber | CISA KEV | known_exploited_vulnerabilities.json | 30 min |
| Cyber | Abuse.ch Feodo | ipblocklist.json | 30 min |
| Cyber | AlienVault OTX | pulses/subscribed (API key required) | 30 min |

## Environment Variables
- `POLYGON_API_KEY` — Polygon.io API key (required for forex + stocks)
- `OTX_API_KEY` — AlienVault OTX API key (optional, for cyber threat pulses)
- `OPENSKY_USERNAME` / `OPENSKY_PASSWORD` — OpenSky Network (optional, for higher rate limits)

## Verification
1. `venv/bin/python main.py`
2. Login at http://localhost:8000/login → redirects to /dashboard
3. WebSocket connects (green status dot)
4. News tab: articles appear within 5 minutes
5. Markets tab: EUR/USD + BTC large charts load within ~2 min (rate-limited staggering)
6. Map tab: Leaflet renders with heatmap dots
7. Kill/restart server → login works, articles persist in SQLite
