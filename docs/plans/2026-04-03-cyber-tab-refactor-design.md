# Cyber Tab Refactor: IODA Outage Detection + Cyber News

**Date:** 2026-04-03
**Status:** Draft — awaiting review
**Reviewed by:** Codex (GPT-5.4), Gemini (3.1 Pro)

## Problem

The current cyber tab collects technical IOC feeds (Feodo C2 IPs, URLhaus malware URLs, C2IntelFeeds) that provide almost zero geopolitical signal. An IP address like `185.220.101.34` tells you nothing about *where* an attack is targeting or *what sector* is affected. The `cyber_escalation.py` keyword classifier tries to extract geo/sector context, but the raw data simply doesn't contain it.

**What we want:** "Internet connectivity in Taiwan dropped 40% — possible disruption to telecom infrastructure" correlated with a news article "Massive DDoS hits Taiwan government sites."

**What we get:** A list of 20 botnet IPs and malware URLs with no geographic or strategic context.

## Key Design Constraint: Isolation

**The cyber tab refactor is fully self-contained.** No changes to other tabs, shared scoring, or shared collectors.

- `scoring.py` — NOT touched. Old cyber scoring pipeline continues to work with stale/empty data until a future refactor.
- `NEWS_FEEDS` / `NewsCollector` — NOT touched. Cyber news is fetched by its own collector within `collectors/cyber.py`.
- `cyber_escalation.py` — left in place as dead code for now (nothing else imports it outside `collectors/cyber.py`).
- `threat_engine.py` — only touched to add a new `"cyber-correlation"` assessment path, which is additive and doesn't change existing behavior.

This means some code is duplicated (e.g., RSS parsing in the cyber collector alongside NewsCollector). That's intentional — we avoid breaking news, military, ships, or threat scoring, and can consolidate later.

## Architecture

```
                        CyberCollector (collectors/cyber.py)
                       ┌─────────────────────────────────────┐
                       │                                     │
  IODA API ──────────▶ │  fetch_ioda()     ──▶ outages[]     │
                       │                                     │
  Cyber RSS feeds ───▶ │  fetch_cyber_news() ──▶ articles[]  │──▶ WS broadcast("cyber", {...})
                       │                                     │         │
  CISA KEV ──────────▶ │  fetch_cisa_kev()  ──▶ cves[]       │         ▼
                       │                                     │   Dashboard cyber tab:
                       │  correlate() ──▶ threat_engine       │   - outage map layer
                       └─────────────────────────────────────┘   - outage list
                                                                 - cyber news feed
                                                                 - CISA KEV panel
```

## Component 1: IODA Outage Collector

**Source:** `https://api.ioda.inetintel.cc.gatech.edu/v2/`

**What it fetches:**
- `GET /v2/outages/alerts?entityType=country&from={now-6h}&until={now}` — real-time alerts
- `GET /v2/outages/events?entityType=country&from={now-24h}&until={now}` — confirmed outage events with duration and score

**Data we get per event:**
```json
{
  "location": "country/TW",
  "location_name": "Taiwan",
  "start": 1743600000,
  "duration": 3600,
  "score": 185000,
  "datasource": "bgp"
}
```

**Processing:**
1. Filter to countries in `IODA_MONITORED_COUNTRIES` (new config, ~20 countries)
2. Map country codes to lat/lon via `COUNTRY_GEO` lookup table (local to cyber module)
3. Normalize score to 1-10 severity scale
4. Label datasource: BGP = routing disruption, merit-nt = telescope, ping = active probing

**Poll interval:** 10 minutes. IODA updates every ~5 min. Handle 429/5xx gracefully — show stale data with "last updated" timestamp.

**Important: Outage != attack.** IODA measures connectivity drops, not hostile intent. An outage could be a cable cut, earthquake, or routine maintenance. The map shows disruption severity only. Hostile confidence is determined separately via LLM correlation (Component 4).

### Country Code → Geo Mapping

Hard-coded lookup table in `collectors/cyber.py`, not shared with `config.py`:

```python
COUNTRY_GEO = {
    "TW": {"name": "Taiwan",        "lat": 24.0,  "lon": 121.0, "region": "Taiwan Strait"},
    "CN": {"name": "China",         "lat": 35.0,  "lon": 105.0, "region": "East Asia"},
    "UA": {"name": "Ukraine",       "lat": 49.0,  "lon": 32.0,  "region": "East Ukraine"},
    "RU": {"name": "Russia",        "lat": 55.75, "lon": 37.6,  "region": "East Ukraine"},
    "IR": {"name": "Iran",          "lat": 32.0,  "lon": 53.0,  "region": "Middle East"},
    "IQ": {"name": "Iraq",          "lat": 33.3,  "lon": 44.4,  "region": "Middle East"},
    "SY": {"name": "Syria",         "lat": 35.0,  "lon": 38.0,  "region": "Middle East"},
    "IL": {"name": "Israel",        "lat": 31.0,  "lon": 35.0,  "region": "Middle East"},
    "PS": {"name": "Palestine",     "lat": 31.9,  "lon": 35.2,  "region": "Middle East"},
    "LB": {"name": "Lebanon",       "lat": 33.9,  "lon": 35.5,  "region": "Middle East"},
    "YE": {"name": "Yemen",         "lat": 15.5,  "lon": 48.5,  "region": "Middle East"},
    "KP": {"name": "North Korea",   "lat": 40.0,  "lon": 127.0, "region": "Korean Peninsula"},
    "KR": {"name": "South Korea",   "lat": 37.5,  "lon": 127.0, "region": "Korean Peninsula"},
    "JP": {"name": "Japan",         "lat": 36.0,  "lon": 138.0, "region": "East Asia"},
    "PH": {"name": "Philippines",   "lat": 12.9,  "lon": 121.8, "region": "South China Sea"},
    "MM": {"name": "Myanmar",       "lat": 19.8,  "lon": 96.2,  "region": "Southeast Asia"},
    "PK": {"name": "Pakistan",      "lat": 30.4,  "lon": 69.3,  "region": "South Asia"},
    "IN": {"name": "India",         "lat": 20.6,  "lon": 79.0,  "region": "South Asia"},
    "SA": {"name": "Saudi Arabia",  "lat": 23.9,  "lon": 45.1,  "region": "Middle East"},
    "ET": {"name": "Ethiopia",      "lat": 9.1,   "lon": 40.5,  "region": "East Africa"},
    "SD": {"name": "Sudan",         "lat": 12.9,  "lon": 30.2,  "region": "East Africa"},
}
```

Non-monitored countries are silently dropped.

## Component 2: Cyber News RSS (self-contained)

**Sources:**
| Feed | URL | Why |
|------|-----|-----|
| The Record | `https://therecord.media/feed` | Best cyber-geo coverage, Recorded Future backed |
| BleepingComputer | `https://www.bleepingcomputer.com/feed/` | Fast reporting on major incidents |
| CyberScoop | `https://cyberscoop.com/feed/` | US gov/policy focus, good attribution context |

**Processing — handled entirely within `CyberCollector`, NOT through `NewsCollector`:**
- Fetch RSS feeds, parse with `feedparser`
- Deduplicate by URL hash (same approach as NewsCollector but independent cache)
- Store in `cyber_news_cache[]` (separate from `articles_cache`)
- Articles are only visible in the cyber tab
- 24-hour window, max 50 articles

## Component 3: CISA KEV (kept from current implementation)

- Same fetch logic as today, just cleaned up
- Shown as a secondary panel in the cyber tab ("Recent Exploited Vulnerabilities")
- No changes to behavior

## Component 4: LLM Correlation

When an IODA outage is detected for a monitored country:
1. Check if any cyber news articles from the last 6 hours mention the same country/region
2. If match found, send to `threat_engine.assess()` with `source="cyber-correlation"`
3. LLM prompt: "Given this internet outage data and these news articles, what is likely happening? Is this a technical failure, a state-directed disruption, or unclear?"
4. High-confidence correlations trigger push notifications

This is the only part that touches `threat_engine.py`, and it's purely additive (new source type).

## What Gets Removed (from cyber collector only)

- **Feodo C2 tracker** — botnet IPs, no geo value
- **URLhaus** — malware distribution URLs, no geo value
- **C2IntelFeeds** — community C2 indicators, no geo value
- **AlienVault OTX** — noisy, contradicts the goal of this refactor

## What Gets Kept Unchanged

- `scoring.py` — no changes
- `cyber_escalation.py` — left as dead code, delete later
- `NewsCollector` / `NEWS_FEEDS` — no changes
- `config.py` `GEO_KEYWORDS` / `MONITORED_REGIONS` — no changes
- All other tabs (news, military, ships, markets, polymarket, pizzint) — no changes

## Dashboard Changes (cyber tab only)

The cyber tab transforms from an IOC table to:

1. **Outage map** — own Leaflet map instance in the cyber tab (not shared with military). Pulsing circles sized by severity, colored by datasource (BGP = red, probing = orange, telescope = yellow). Click for details.
2. **Active outages panel** — list: country, duration, severity, datasource, "last updated" timestamp
3. **Cyber news feed** — scrollable list of articles from cyber-specific RSS feeds
4. **CISA KEV panel** — recent exploited vulnerabilities (kept from current)
5. **Stats bar** — active outages count, countries affected, CISA KEV count

## WebSocket Payload

New payload shape, broadcast as `"cyber"`:

```json
{
  "outages": [
    {
      "country_code": "TW",
      "country_name": "Taiwan",
      "region": "Taiwan Strait",
      "lat": 24.0,
      "lon": 121.0,
      "severity": 7,
      "datasource": "bgp",
      "start": 1743600000,
      "duration": 3600,
      "raw_score": 185000
    }
  ],
  "cyber_news": [
    {
      "title": "...",
      "url": "...",
      "source": "The Record",
      "published": "...",
      "summary": "..."
    }
  ],
  "cves": [
    {
      "cve_id": "CVE-2026-1234",
      "title": "...",
      "severity": "Critical",
      "date_added": "2026-04-03"
    }
  ],
  "stats": {
    "active_outages": 3,
    "countries_affected": 2,
    "new_cves": 1
  },
  "correlations": [
    {
      "country": "Taiwan",
      "outage_severity": 7,
      "matched_articles": 2,
      "llm_assessment": "Likely state-directed disruption targeting telecom",
      "confidence": "high"
    }
  ]
}
```

The old IOC-centric payload shape is replaced. The frontend JS for the cyber tab is rewritten to consume this new shape.

## File Changes

| File | Change | Risk |
|------|--------|------|
| `collectors/cyber.py` | Rewrite: IODA + cyber RSS + CISA KEV + correlation | Contained to cyber tab |
| `config.py` | Add IODA config entries only (no changes to NEWS_FEEDS) | Low |
| `templates/dashboard.html` | Cyber tab HTML: map div + panels | Cyber tab only |
| `static/js/cyber.js` | New: IODA map, outage list, cyber news, KEV panel | New file |
| `threat_engine.py` | Add `"cyber-correlation"` source handling | Additive only |

Files NOT changed: `scoring.py`, `cyber_escalation.py`, `collectors/news.py`, `ws_manager.py`, `database.py`, all other collector files, all other tab JS/HTML.

## New Config Entries

```python
# IODA Internet Outage Detection
IODA_API_BASE = "https://api.ioda.inetintel.cc.gatech.edu/v2"
IODA_POLL_INTERVAL = 600  # 10 minutes
IODA_ALERT_LOOKBACK = 21600  # 6 hours
IODA_EVENT_LOOKBACK = 86400  # 24 hours

# Cyber-specific news feeds (NOT added to NEWS_FEEDS — fetched by CyberCollector)
CYBER_NEWS_FEEDS = {
    "The Record": "https://therecord.media/feed",
    "BleepingComputer": "https://www.bleepingcomputer.com/feed/",
    "CyberScoop": "https://cyberscoop.com/feed/",
}
```

## Review Feedback Addressed

| Concern (Codex/Gemini) | Resolution |
|-------------------------|------------|
| `scoring.py` breaks if `cyber_escalation.py` deleted | Not touching `scoring.py`. Old pipeline stays. |
| `NEWS_FEEDS` has no category support | Not using `NEWS_FEEDS`. Cyber news is self-contained. |
| WebSocket payload schema change breaks frontend | Only cyber tab frontend is rewritten. Other tabs unaffected. |
| Country code → region gap | `COUNTRY_GEO` lookup table local to cyber module. |
| Outage != attack false positives | Two-tier model: map shows disruption only, hostile confidence requires LLM correlation with news. |
| OTX noise contradicts refactor goal | Dropped entirely. |
