# Eye of Providence - Feature Tracker

## Phase 1: Core Infrastructure
- [x] F1.1: WebSocket server — ConnectionManager with connect/disconnect/broadcast
- [x] F1.2: Background task framework — BaseCollector abstract class with async run() loop
- [x] F1.3: Centralized config — config.py with all feed URLs, API endpoints, intervals
- [x] F1.4: Dark-themed dashboard shell — base.html with navbar and 5-tab bar
- [x] F1.5: Tab switching UI — dashboard.js with URL hash persistence
- [x] F1.6: WebSocket client — ws.js with auto-reconnect and connection status indicator
- [x] F1.7: Dashboard CSS — dark theme with card components and responsive grid
- [x] F1.8: Protected /dashboard route — requires session auth
- [x] F1.9: Static file serving — mounted at /static
- [x] F1.10: Updated dependencies — feedparser, httpx, websockets added

## Phase 2: News Module
- [x] F2.1: RSS feed collector — BBC World, Al Jazeera, CNA every 5 min
- [x] F2.2: Article normalization — title, summary, URL, source, publish date
- [x] F2.3: Deduplication — URL hash-based skip
- [x] F2.4: Geo-tagging — keyword→region lookup with lat/lon
- [x] F2.5: Article persistence — Article SQLAlchemy model
- [x] F2.6: WebSocket broadcast — {module: "news", data: [...]}
- [x] F2.7: News tab UI — scrolling card feed with source badge and threat indicator
- [x] F2.8: Source filter — buttons to filter by source
- [x] F2.9: REST API endpoint — GET /api/news

## Phase 3: Markets Module
- [x] F3.1: Forex data collector — Polygon.io API (EUR/USD, GBP/USD, USD/JPY)
- [x] F3.2: Stock data collector — Polygon.io API (SPY, QQQ, DIA, TSLA)
- [x] F3.3: Crypto data collector — CoinGecko API (BTC, ETH) with 30-day chart history
- [x] F3.4: Fear & Greed Index — from alternative.me every 15 min
- [x] F3.5: WebSocket broadcast — {module: "markets", data: {forex, crypto, stocks, ...}}
- [x] F3.6: TradingView-style charts — canvas rendering with line, filled area, prev close reference, price/time axes
- [x] F3.7: Primary layout — EUR/USD + Bitcoin as large side-by-side charts
- [x] F3.8: Secondary layout — other forex, crypto, stocks as smaller chart cards
- [x] F3.9: Market ticker bar — horizontal scrolling ticker with all instruments
- [x] F3.10: Fear & Greed gauge — 0-100 scale with color gradient
- [x] F3.11: Rate limit handling — 13s stagger between Polygon requests (free tier: 5 req/min)
- [x] F3.12: Forex 4-decimal precision — proper formatting for currency pairs
- [x] F3.13: REST API endpoint — GET /api/markets

## Phase 4: Military Module
- [x] F4.1: Aircraft tracker — OpenSky Network for 5 monitored regions
- [x] F4.2: Region filtering — configurable bounding boxes in config.py
- [x] F4.3: Asset normalization — callsign, lat, lon, altitude, heading, source, origin_country
- [x] F4.4: WebSocket broadcast — {module: "military", data: [...]}
- [x] F4.5: Asset table UI — table with callsign, country, altitude, heading, region
- [x] F4.6: Activity counter — region summary cards with asset counts
- [x] F4.7: REST API endpoint — GET /api/military

## Phase 5: Cyber Module
- [x] F5.1: CISA KEV collector — Known Exploited Vulnerabilities every 30 min
- [x] F5.2: Abuse.ch Feodo collector — botnet C2 blocklist every 30 min
- [x] F5.3: AlienVault OTX collector — threat pulses (graceful skip if no API key)
- [x] F5.4: Threat normalization — type, title, severity, source, ioc_count, timestamp
- [x] F5.5: ThreatEvent persistence — ThreatEvent SQLAlchemy model
- [x] F5.6: WebSocket broadcast — {module: "cyber", data: [...]}
- [x] F5.7: Threat cards UI — severity-sorted with color coding (Critical/High/Medium/Low)
- [x] F5.8: Summary stats bar — total IOCs, active campaigns, new CVEs, threat level
- [x] F5.9: REST API endpoint — GET /api/cyber

## Phase 6: Geographic Map + Threat Scoring
- [x] F6.1: Leaflet map — dark CARTO tiles, world view
- [x] F6.2: News heatmap layer — leaflet.heat with geo-tagged article intensity
- [x] F6.3: Military markers — circleMarkers with tooltip (callsign, altitude, heading)
- [x] F6.4: Threat scoring algorithm — keyword weights + volume + military + cyber → 0-100
- [x] F6.5: Region threat overlay — color-coded circles for 5 monitored regions
- [x] F6.6: Region tooltip — name and threat score on click
- [x] F6.7: Layer toggle controls — checkboxes for heatmap, military, regions
- [x] F6.8: Auto-refresh — real-time updates via WebSocket
- [x] F6.9: REST API endpoint — GET /api/threats
