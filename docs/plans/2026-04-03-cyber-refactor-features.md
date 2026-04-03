# Cyber Tab Refactor — Feature List & Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace the IOC-centric cyber tab with IODA internet outage detection, cyber-specific news RSS, retained CISA KEV, and LLM correlation — all self-contained within the cyber tab.

**Architecture:** The `CyberCollector` is fully rewritten to fetch from three sources (IODA, cyber RSS, CISA KEV) and broadcast a new payload shape via WebSocket. The cyber tab gets its own Leaflet map for outage visualization, a cyber news feed, and a CISA KEV panel. LLM correlation is additive to `threat_engine.py`. No other tabs or shared components are modified.

**Tech Stack:** Python/FastAPI (backend), Leaflet.js (map), feedparser (RSS), httpx (API calls), existing WebSocket infrastructure.

---

## Review Fixes (from Codex/Gemini)

1. **`cyber_cache` shape change breaks `scoring.py`** — `main.py:487` passes `cyber_cache` to `compute_region_scores()` which expects `list[dict]`. Fix: keep a `cyber_events_legacy = []` list that stays empty (old IOC events are gone) so scoring still works. `cyber_cache` becomes a `dict` for the new payload. Update `main.py:485` to import `cyber_events_legacy` instead.
2. **`source="cyber-correlation"` bypasses config** — `threat_engine.py:156` checks `config.sources[source]`. Fix: use `source="cyber"` for correlations so the existing toggle controls it.
3. **`correlations[]` missing from broadcast** — Add to payload.
4. **DB persistence** — Skip for new data. Old `ThreatEvent` model doesn't fit. Remove the DB persist block from the rewritten collector.
5. **`last_updated` timestamp** — Add to broadcast payload and render in UI.
6. **Lazy-init map** — Use MutationObserver in `cyber.js` (same pattern as `map.js:600-616`).

---

## Feature List

### Feature 1: Config entries for IODA and cyber RSS feeds

**Files:**
- Modify: `config.py` (add IODA and cyber RSS config after existing cyber config ~line 9)

**What:** Add `IODA_API_BASE`, `IODA_POLL_INTERVAL`, `IODA_ALERT_LOOKBACK`, `IODA_EVENT_LOOKBACK`, and `CYBER_NEWS_FEEDS` dict. Change `CYBER_POLL_INTERVAL` from 1800 to 600 (10 min, matching IODA update frequency). Remove `FEODO_URL`, `URLHAUS_CSV_URL`, `C2INTEL_CSV_URL`.

```python
# Replace CYBER_POLL_INTERVAL
CYBER_POLL_INTERVAL = 600  # 10 minutes (IODA updates every ~5 min)

# IODA Internet Outage Detection
IODA_API_BASE = "https://api.ioda.inetintel.cc.gatech.edu/v2"
IODA_ALERT_LOOKBACK = 21600   # 6 hours
IODA_EVENT_LOOKBACK = 86400   # 24 hours

# Cyber-specific news feeds (fetched by CyberCollector, NOT NewsCollector)
CYBER_NEWS_FEEDS = {
    "The Record": "https://therecord.media/feed",
    "BleepingComputer": "https://www.bleepingcomputer.com/feed/",
    "CyberScoop": "https://cyberscoop.com/feed/",
}
```

Remove these lines (~81-85):
```python
# DELETE:
FEODO_URL = "https://feodotracker.abuse.ch/downloads/ipblocklist.json"
URLHAUS_CSV_URL = "https://urlhaus.abuse.ch/downloads/csv_recent/"
C2INTEL_CSV_URL = "https://raw.githubusercontent.com/drb-ra/C2IntelFeeds/master/feeds/IPC2s-30day.csv"
```

Keep `CISA_KEV_URL` and `OTX_PULSE_URL`/`OTX_API_KEY` (OTX stays as dead config for now).

---

### Feature 2: Rewrite `collectors/cyber.py` — IODA outage fetcher

**Files:**
- Rewrite: `collectors/cyber.py`

**What:** Replace the entire collector. New class fetches from three sources: IODA API, cyber news RSS, and CISA KEV. Contains its own `COUNTRY_GEO` mapping table. Broadcasts a new payload shape.

**IODA fetch logic:**
```python
async def _fetch_ioda_alerts(self, client):
    """Fetch real-time outage alerts for monitored countries."""
    now = int(time.time())
    params = {
        "entityType": "country",
        "from": now - IODA_ALERT_LOOKBACK,
        "until": now,
    }
    resp = await client.get(f"{IODA_API_BASE}/outages/alerts", params=params)
    resp.raise_for_status()
    data = resp.json().get("data", [])
    # Filter to monitored countries, only critical alerts
    outages = []
    for alert in data:
        entity = alert.get("entity", {})
        code = entity.get("code", "")
        if code not in COUNTRY_GEO:
            continue
        if alert.get("level") != "critical":
            continue
        # Deduplicate — keep highest-score alert per country+datasource
        ...
    return outages

async def _fetch_ioda_events(self, client):
    """Fetch confirmed outage events."""
    now = int(time.time())
    params = {
        "entityType": "country",
        "from": now - IODA_EVENT_LOOKBACK,
        "until": now,
    }
    resp = await client.get(f"{IODA_API_BASE}/outages/events", params=params)
    resp.raise_for_status()
    data = resp.json().get("data", [])
    events = []
    for event in data:
        loc = event.get("location", "")  # "country/TW"
        code = loc.split("/")[-1] if "/" in loc else loc
        if code not in COUNTRY_GEO:
            continue
        geo = COUNTRY_GEO[code]
        events.append({
            "country_code": code,
            "country_name": geo["name"],
            "region": geo["region"],
            "lat": geo["lat"],
            "lon": geo["lon"],
            "severity": _normalize_score(event.get("score", 0)),
            "datasource": event.get("datasource", "unknown"),
            "start": event.get("start", 0),
            "duration": event.get("duration", 0),
            "raw_score": event.get("score", 0),
        })
    return events
```

**Cyber news fetch logic:**
```python
async def _fetch_cyber_news(self, client):
    """Fetch cyber-specific RSS feeds (self-contained, not via NewsCollector)."""
    articles = []
    for source, url in CYBER_NEWS_FEEDS.items():
        try:
            resp = await client.get(url)
            if resp.status_code != 200:
                continue
            feed = feedparser.parse(resp.content)
            for entry in feed.entries[:15]:
                pub_parsed = entry.get("published_parsed")
                if pub_parsed:
                    pub_ts = calendar.timegm(pub_parsed)
                    if time.time() - pub_ts > 24 * 3600:
                        continue
                else:
                    pub_ts = None
                url_hash = hashlib.sha256(entry.get("link", "").encode()).hexdigest()[:16]
                if url_hash in self._seen_urls:
                    continue
                self._seen_urls.add(url_hash)
                articles.append({
                    "title": entry.get("title", ""),
                    "url": entry.get("link", ""),
                    "source": source,
                    "published": entry.get("published", ""),
                    "published_ts": pub_ts,
                    "summary": (entry.get("summary", "") or "")[:300],
                })
        except Exception as e:
            logger.error(f"[cyber] RSS {source}: {e}")
    return articles
```

**CISA KEV fetch:** Keep existing logic, simplified — just the CISA KEV fetch from the current collector.

**Broadcast payload shape:**
```python
await manager.broadcast("cyber", {
    "outages": outages,          # IODA events
    "cyber_news": cyber_news,    # RSS articles
    "cves": cves,                # CISA KEV
    "stats": {
        "active_outages": len(outages),
        "countries_affected": len(set(o["country_code"] for o in outages)),
        "new_cves": new_cve_count,
    },
})
```

**`COUNTRY_GEO` table:** Hard-coded dict at module level (21 countries from design doc).

**`_normalize_score(raw)` function:** Map IODA's raw score (which varies wildly) to 1-10 severity. Use log-scale bucketing since scores range from ~10k to ~2M.

---

### Feature 3: REST API endpoint update

**Files:**
- Modify: `main.py:440-446` (the `/api/cyber` endpoint)

**What:** Update the `/api/cyber` endpoint to return the new data shape (outages, cyber_news, cves, stats) instead of the old IOC-centric shape.

```python
@app.get("/api/cyber")
@limiter.limit("60/minute")
async def api_cyber(request: Request):
    if not _require_auth(request):
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    from collectors.cyber import cyber_cache
    return JSONResponse(cyber_cache)
```

The `cyber_cache` changes from `list[dict]` to `dict` with the new payload shape. The `stats_cache` merges into `cyber_cache["stats"]`.

---

### Feature 4: Dashboard HTML — cyber tab layout

**Files:**
- Modify: `templates/dashboard.html:54-64` (the `<!-- Cyber Tab -->` section)

**What:** Replace the current IOC table with: outage map div, stats bar, outage list panel, cyber news panel, CISA KEV panel.

```html
<!-- Cyber Tab -->
<div id="tab-cyber" class="tab-content">
    <!-- Stats bar -->
    <div id="cyber-stats" class="cyber-stats"></div>

    <!-- Two-column layout: map + panels -->
    <div style="display:grid; grid-template-columns:1fr 1fr; gap:12px; margin-top:12px;">
        <!-- Left: Outage Map -->
        <div>
            <div id="cyber-map" style="height:400px; border-radius:8px; border:1px solid var(--border);"></div>
            <div id="cyber-outage-list" style="margin-top:12px;"></div>
        </div>
        <!-- Right: Cyber News + KEV -->
        <div>
            <div id="cyber-news-feed" style="max-height:420px; overflow-y:auto;"></div>
            <div id="cyber-kev-panel" style="margin-top:12px; max-height:200px; overflow-y:auto;"></div>
        </div>
    </div>

    <!-- Alerts toggle (kept) -->
    <div style="margin-top:12px;">
        <label style="font-size:12px; display:flex; align-items:center; gap:6px; color:var(--text-secondary); cursor:pointer;">
            <input type="checkbox" id="cyber-alerts-toggle" style="accent-color:var(--accent);">
            Push notifications for cyber correlations
        </label>
    </div>
</div>
```

---

### Feature 5: Frontend JS — cyber tab rewrite (`static/js/cyber.js`)

**Files:**
- Rewrite: `static/js/cyber.js`

**What:** Complete rewrite. Handles:
1. **Leaflet map** — own map instance in `#cyber-map`, dark tile layer, pulsing circle markers for outages
2. **Stats bar** — active outages, countries affected, new CVEs
3. **Outage list** — rendered below map, showing country, duration, severity, datasource
4. **Cyber news feed** — rendered in right column, clickable article cards
5. **CISA KEV panel** — rendered below news, CVE cards
6. **WebSocket handler** — listens for `"cyber"` messages with new payload shape
7. **Lazy init** — map initializes only when cyber tab becomes active (same pattern as `map.js`)

**Map marker style:**
- Pulsing circle markers (CSS animation), sized by severity (radius 10-30px)
- Color by datasource: BGP = `#ff4444`, active probing = `#ff9800`, telescope = `#ffeb3b`
- Tooltip on hover: country name, severity, datasource, duration, start time

---

### Feature 6: LLM correlation in threat engine

**Files:**
- Modify: `threat_engine.py` (add handling for `source="cyber-correlation"`)
- Modify: `collectors/cyber.py` (call `threat_engine.assess` when correlation found)

**What:** After fetching both IODA outages and cyber news, check for geographic overlap:
- For each outage country, scan cyber news articles for mentions of that country name
- If match found, call `threat_engine.assess("cyber-correlation", title, body)` where `title` summarizes the correlation and `body` includes both the outage data and matching articles
- The threat engine's existing LLM pipeline handles the rest (scoring, notification)

This is additive — no changes to existing threat engine behavior for other sources.

```python
# In CyberCollector.collect(), after fetching both:
async def _correlate(self, outages, articles):
    """Check for IODA outage + cyber news overlap. Send to LLM if found."""
    for outage in outages:
        country = outage["country_name"].lower()
        matches = [a for a in articles if country in a["title"].lower() or country in a.get("summary", "").lower()]
        if not matches:
            continue
        title = f"Internet outage in {outage['country_name']} ({outage['datasource']}) with {len(matches)} related cyber news articles"
        body = f"IODA detected a severity {outage['severity']}/10 internet disruption in {outage['country_name']} "
        body += f"(datasource: {outage['datasource']}, duration: {outage['duration']}s). "
        body += "Related articles: " + "; ".join(a["title"] for a in matches[:3])
        try:
            await threat_engine.assess("cyber-correlation", title, body,
                                       extra={"geo_region": outage["region"],
                                              "country": outage["country_name"],
                                              "outage_severity": outage["severity"]})
        except Exception as e:
            logger.error(f"[cyber] Correlation assess error: {e}")
```

---

## Implementation Order

1. **Feature 1** — Config entries (foundation, everything else imports from here)
2. **Feature 2** — Rewrite `collectors/cyber.py` (core backend logic)
3. **Feature 3** — REST API update (tiny change, makes new data available)
4. **Feature 4** — Dashboard HTML (layout for new UI)
5. **Feature 5** — Frontend JS rewrite (renders the new data)
6. **Feature 6** — LLM correlation (polish, adds intelligence layer)

## Review Checkpoints

- After Features 1-3: backend review (Codex + Gemini) — does the collector work, is the API shape right?
- After Features 4-5: frontend review — does the UI render correctly?
- After Feature 6: final review — does correlation logic make sense?

## Not Changed

- `scoring.py` — untouched
- `cyber_escalation.py` — left as dead code
- `collectors/news.py` — untouched
- `templates/dashboard.html` — only the cyber tab section changes
- All other JS files — untouched
- `main.py` — only the `/api/cyber` endpoint changes
- `threat_engine.py` — only additive (new source type)
