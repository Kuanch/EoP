# API Reference

**Base URL**: `https://kuanchlee.com` (Cloudflare Tunnel) or `http://192.168.0.148:8000` (LAN)

All API endpoints require authentication via `session_token` cookie unless noted otherwise. Rate limits are per-IP.

## HTML Routes

### `GET /`
Redirects to `/dashboard` if authenticated, otherwise to `/login`.

### `GET /index`
Redirects to `/dashboard`.

### `GET /dashboard`
Main dashboard page.
- **Auth required**: Yes (redirects to `/login` if not authenticated)

---

## Authentication

### `GET /login`
Login page.
- **Auth required**: No
- **Response**: HTML login form with CSRF token

### `POST /login`
Authenticate user and set session cookie.
- **Auth required**: No
- **Rate limit**: 10/min
- **Brute force**: 5 failed attempts → 1h IP lockout
- **Content-Type**: `application/x-www-form-urlencoded`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `username` | string | Yes | Account username |
| `password` | string | Yes | Account password |
| `csrf_token` | string | Yes | CSRF token from login form |

**Success**: 302 redirect to `/dashboard`, sets `session_token` cookie (HttpOnly, SameSite=Lax, 24h max age; `Secure` flag only when `ENVIRONMENT=production`)

**Failure**: Re-renders login page with inline error message (invalid credentials, expired CSRF, or rate limited)

### `POST /logout`
End session and clear cookie.
- **Auth required**: Yes
- **Body**: `csrf_token` (form field)
- **Response**: 302 redirect to `/login`

---

## WebSocket

### `WS /ws`
Real-time data broadcast to all authenticated clients.
- **Auth required**: Yes (session cookie)
- **Origin validation**: Must match `ALLOWED_ORIGINS` env var (comma-separated allowlist)

**Message format** (server → client):
```json
{
  "module": "news|markets|military|cyber|ships|pizzint|polymarket",
  "data": <module-specific payload>
}
```

Modules broadcast at different intervals — see individual endpoint sections for data structures.

---

## News

### `GET /api/news`
Latest news articles.
- **Rate limit**: 60/min
- **Response**: Array (last 100 from in-memory cache, append order)
- **Note**: Served from in-memory cache (max 200 articles), not from database

```json
[
  {
    "url_hash": "a1b2c3d4e5f6g7h8",
    "title": "Article headline",
    "summary": "First 300 chars of article...",
    "source": "BBC World",
    "url": "https://...",
    "published": "Thu, 27 Feb 2026 12:00:00 GMT",
    "geo_region": "Taiwan Strait",
    "geo_lat": 24.0,
    "geo_lon": 121.0,
    "threat_score": 3.5,
    "collected_at": "2026-02-27T12:00:00"
  }
]
```

**WebSocket module**: `news` — broadcasts on each collection cycle (every 5 min). Same data format.

---

## Markets

### `GET /api/markets`
Financial market data.
- **Rate limit**: 60/min

```json
{
  "forex": {
    "EUR/USD": {
      "symbol": "C:EURUSD",
      "price": 1.0845,
      "change": 0.0012,
      "change_pct": 0.11,
      "prev_close": 1.0833,
      "open": 1.0835,
      "high": 1.0860,
      "low": 1.0820,
      "is_open": true
    }
  },
  "stocks": {
    "S&P 500": {
      "symbol": "SPY",
      "price": 502.15,
      "change": 3.20,
      "change_pct": 0.64,
      "prev_close": 498.95,
      "open": 499.10,
      "high": 503.00,
      "low": 498.50,
      "is_open": true
    }
  },
  "crypto": {
    "Bitcoin": {
      "name": "Bitcoin",
      "price": 84500.00,
      "change_pct": 2.3,
      "is_open": true,
      "prev_close": 82600.00
    }
  },
  "fear_greed": {
    "value": 45,
    "classification": "Fear"
  },
  "intraday": {
    "SPY": [
      {"t": 1709035200000, "p": 502.15}
    ]
  }
}
```

**WebSocket module**: `markets` — broadcasts every 60s.

---

## Military

### `GET /api/military`
Aircraft tracked across monitored regions.
- **Rate limit**: 60/min
- **Response**: Array of aircraft objects

```json
[
  {
    "callsign": "CES2156",
    "type": "aircraft",
    "lat": 24.5,
    "lon": 121.3,
    "altitude": 10668,
    "heading": 45,
    "region": "Taiwan Strait",
    "source": "OpenSky",
    "icao24": "780a1f",
    "origin_country": "China"
  }
]
```

**WebSocket module**: `military` — broadcasts on each collection cycle (every 30s). Initial data loaded via HTTP on page load.

**Monitored regions**: Taiwan Strait, East Ukraine, Middle East, Korean Peninsula, South China Sea.

### Data Sources

Aircraft data is merged from two providers, deduplicated by ICAO24 hex code:

| Source | Endpoint | Auth | Coverage | Notes |
|--------|----------|------|----------|-------|
| **OpenSky Network** | Bounding box queries per region | OAuth2 (client credentials), falls back to anonymous | Good in East Asia; sparse in Middle East, conflict zones | Free tier (anonymous: stricter rate limits), 30s poll interval, 5s delay between region queries |
| **adsb.fi** | `/v3/lat/{lat}/lon/{lon}/dist/250` per region center | None (free, no key) | Good in East Asia; no receivers in Middle East, Ukraine, South China Sea | 1 req/sec rate limit, 250 NM max radius |

When duplicates exist (same ICAO24 from both sources), adsb.fi takes priority as a secondary validation source. Altitude from adsb.fi is converted from feet to meters to match OpenSky format.

### Coverage Limitations

Both OpenSky and adsb.fi are **community-driven ADS-B networks** that depend on volunteer ground receivers. Coverage is inherently uneven:

- **Strong coverage**: Taiwan Strait, Korean Peninsula (dense feeder networks in Taiwan, Japan, South Korea)
- **Weak/no coverage**: Middle East, East Ukraine, South China Sea (few or no ground receivers; conflict zones often have transponders disabled)

Satellite-based ADS-B (e.g., FlightRadar24, Aireon) would improve coverage in underserved regions but requires paid commercial APIs.

### Alternatives Evaluated

| Provider | Type | Cost | Why Not Used |
|----------|------|------|--------------|
| **ADS-B Exchange** | Ground-based community | Paid API | Requires API key purchase |
| **FlightRadar24** | Ground + satellite | Commercial | Restricted API, expensive |
| **ADSB-One** | Ground-based community | Free | Similar coverage gaps as adsb.fi |
| adsb.fi `/v2/mil` | Military-tagged only | Free | Only ~140 aircraft globally, none in our monitored regions |

---

## Cyber

### `GET /api/cyber`
Cyber threat events and statistics.
- **Rate limit**: 60/min

```json
{
  "events": [
    {
      "type": "cve",
      "title": "CVE-2026-12345",
      "severity": "Critical",
      "source": "CISA KEV",
      "description": "Remote code execution in...",
      "ioc_count": 1,
      "timestamp": "2026-02-27T10:00:00"
    }
  ],
  "stats": {
    "total_iocs": 156,
    "active_campaigns": 3,
    "new_cves": 12,
    "threat_level": "Medium"
  }
}
```

**Event types**: `cve` (CISA KEV), `c2` (Abuse.ch Feodo), `pulse` (AlienVault OTX)

**Severity levels**: Critical, High, Medium, Low

**Threat level thresholds**:
- Critical: `total_iocs > 100` or `new_cves > 5`
- High: `total_iocs > 50` or `new_cves > 2`
- Medium: `total_iocs > 20`
- Low: otherwise

**WebSocket module**: `cyber` — broadcasts every 30 min.

---

## Ships

### `GET /api/ships`
AIS ship tracking data.
- **Rate limit**: 60/min

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `filter` | string | `china` | Preset filter: `china`, `known`, `moving`, `notable`, `all` |
| `country` | string | — | Country name filter (case-insensitive partial match) |

**Filter presets**:
- `china` — Chinese-flagged vessels only
- `known` — Moving vessels (SOG >= 0.5 kn) with known vessel type (not "Other")
- `moving` — Speed >= 0.5 knots
- `notable` — Excludes stationary unknown-type vessels (keeps everything else)
- `all` — No filtering

```json
[
  {
    "mmsi": "413123456",
    "name": "DONG FANG 3",
    "lat": 24.15,
    "lon": 118.08,
    "sog": 12.5,
    "cog": 225.0,
    "heading": 223,
    "vessel_type": 55,
    "vessel_type_name": "Law Enforcement",
    "nav_status": 0,
    "source": "TW-MPB",
    "country": "China"
  }
]
```

**Vessel types**: Fishing (30), Towing (31-32), Military (35), Sailing (36), Pleasure (37), Pilot (50), SAR (51), Tug (52), Law Enforcement (55), Cargo (70-79), Tanker (80-89)

**Country**: Derived from MMSI Maritime Identification Digits (first 3 digits)

**WebSocket module**: `ships` — broadcasts every 5s (batched from Taiwan MPB + AISstream).

---

## Polymarket

### `GET /api/polymarket`
Geopolitical prediction market odds.
- **Rate limit**: 60/min
- **Response**: Array sorted by probability (descending)

```json
[
  {
    "slug": "will-china-invade-taiwan-before-2027",
    "question": "Will China invade Taiwan before 2027?",
    "probability": 0.04,
    "volume": 1250000,
    "volume_24h": 15000,
    "liquidity": 45000,
    "end_date": "2027-01-01",
    "image": "https://...",
    "active": true
  }
]
```

**Tracked events**: China-Taiwan invasion, US-China clash, NK-SK invasion, US-Russia clash, US Latin America invasion, US civil war, nuclear detonation.

**WebSocket module**: `polymarket` — broadcasts every 5 min.

---

## PizzINT

### `GET /api/pizzint`
Pentagon Pizza Index — delivery activity near the Pentagon as a proxy for operational tempo.
- **Rate limit**: 60/min

```json
{
  "optempo_level": 5,
  "optempo_label": "Business As Usual",
  "assessment": "Normal activity levels observed...",
  "metro_ratio": 1.02,
  "corridors": [
    {
      "id": "pentagon-city",
      "tier": 1,
      "deviation": 0.05,
      "speed_ratio": 0.98
    }
  ],
  "polymarket": [
    {
      "slug": "us-x-china-military-clash-before-2027",
      "label": "US-China clash",
      "probability": 0.08
    }
  ],
  "timestamp": "2026-02-27T12:00:00Z"
}
```

**OPTEMPO levels**: 0 (highest alert) → 5 (business as usual)

**WebSocket module**: `pizzint` — broadcasts every 5 min.

---

## Threats

### `GET /api/threats`
Regional threat scores.
- **Rate limit**: 60/min
- **Response**: Object mapping region name → score (0-100)

```json
{
  "Taiwan Strait": 42,
  "East Ukraine": 67,
  "Middle East": 55,
  "Korean Peninsula": 18,
  "South China Sea": 31
}
```

### `GET /api/threats/feed`
Threat assessment feed (items with `final_score >= 5`).
- **Rate limit**: 60/min
- **Response**: Array (newest first, max 100)

```json
[
  {
    "timestamp": 1740652800.123,
    "source": "news",
    "title": "Article headline",
    "text": "Full text assessed...",
    "rule_score": 8,
    "llm_score": 7,
    "llm_threat_type": "Military Escalation",
    "llm_rationale": "此文章涉及...",
    "final_score": 8,
    "notified": true
  }
]
```

### `GET /api/threats/stats`
Daily threat statistics.
- **Rate limit**: 60/min

```json
{
  "threats_today": 12,
  "notifications_sent": 3,
  "llm_calls": 8,
  "day": "2026-02-27"
}
```

### `GET /api/threats/config`
Current threat engine configuration.
- **Rate limit**: 30/min

```json
{
  "keyword_rules": {
    "war": 8,
    "invasion": 7,
    "nuclear": 7,
    "missile": 6
  },
  "llm_threshold": 5,
  "notify_threshold": 8,
  "llm_enabled": false,
  "llm_prompt": "You are a geopolitical...",
  "cooldown_minutes": 60,
  "sources": {
    "news": true,
    "cyber": false,
    "pizzint": true
  }
}
```

### `POST /api/threats/config`
Update threat engine configuration. Partial updates supported.
- **Rate limit**: 10/min
- **Content-Type**: `application/json`

| Field | Type | Range | Description |
|-------|------|-------|-------------|
| `keyword_rules` | object | values: 0-10 | Keyword → weight mapping (values must be numeric, 0-10) |
| `llm_threshold` | number | 1-15 | Minimum rule score to trigger LLM assessment |
| `notify_threshold` | number | 1-10 | Minimum final score to send notification |
| `llm_enabled` | boolean | — | Enable/disable LLM classification |
| `llm_prompt` | string | max 2000 chars | System prompt for Claude Haiku (`claude-haiku-4-5-20251001`) |
| `cooldown_minutes` | number | 1-120 | Per-item notification cooldown |
| `sources` | object | — | Source toggles: `{news, cyber, pizzint}` (boolean values) |

**Success**: `{"status": "ok"}`

**Error**: `{"error": "error message"}` with 400 status

**Note**: `POST /api/threats/config` overwrites `threat_rules.json` on disk.

---

## Health

### `GET /api/health/data`
Data source freshness and upstream health status.
- **Rate limit**: 60/min

```json
{
  "news": {
    "status": "fresh",
    "last_success_ago": 42.3,
    "last_error_msg": null,
    "collect_count": 15,
    "error_count": 0
  },
  "markets": {
    "status": "stale",
    "last_success_ago": 185.7,
    "last_error_msg": "HTTPStatusError: 429",
    "collect_count": 120,
    "error_count": 2
  }
}
```

**Status values**: `fresh` (within 2x poll interval), `stale` (2-8x interval), `down` (>8x interval), `error` (never succeeded, has errors), `no_data` (never collected)

**Tracked sources**: news, markets, military, cyber, ships, pizzint, polymarket

**UI**: The navbar displays colored dots for each source — green (fresh), yellow (stale), red (down/error), grey (no data). Hover for details. Polled every 30s.

---

## Error Responses

All API errors follow this format:

```json
{
  "error": "Error description"
}
```

| Status | Meaning |
|--------|---------|
| 401 | Not authenticated (missing/expired session) |
| 403 | CSRF token invalid |
| 429 | Rate limit exceeded |
| 400 | Invalid request body |
| 500 | Internal server error |

## Rate Limits

| Endpoint | Limit |
|----------|-------|
| `POST /login` | 10/min |
| `GET /api/*` | 60/min |
| `GET /api/threats/config` | 30/min |
| `POST /api/threats/config` | 10/min |

Rate limit headers are included in responses: `X-RateLimit-Limit`, `X-RateLimit-Remaining`, `X-RateLimit-Reset`.

## Timestamp Formats

| Endpoint | Format |
|----------|--------|
| `/api/news` `collected_at` | ISO 8601 string |
| `/api/news` `published` | RFC 2822 string (from RSS) |
| `/api/threats/feed` `timestamp` | Unix epoch seconds (float) |
| `/api/cyber` `timestamp` | ISO 8601 string |
| `/api/pizzint` `timestamp` | ISO 8601 string |

## Static Assets

`/static/js/` and `/static/css/` are protected by authentication middleware. Unauthenticated requests return 401.
