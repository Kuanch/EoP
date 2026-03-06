# World Monitor-Inspired Improvements Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add high-value free data sources inspired by World Monitor to enrich EoP's situational awareness across maritime, natural disaster, geopolitical, cyber, and infrastructure domains.

**Architecture:** Each new data source gets a dedicated collector (inheriting `BaseCollector`), a REST endpoint, WebSocket broadcast, and a UI panel/map layer. We prioritize free, no-auth APIs first. Static datasets (trade routes, ports) are embedded as JSON data files.

**Tech Stack:** Python/FastAPI (backend collectors), Leaflet.js (map layers), vanilla JS (UI panels), httpx (async HTTP)

---

## Priority Tiers

- **Tier 1 (High value, zero auth):** NGA Maritime Warnings, USGS Earthquakes, Trade Routes (static), Additional Cyber Feeds
- **Tier 2 (High value, free auth):** GDELT Geo-events, GPS Jamming (gpsjam.org)
- **Tier 3 (Nice to have):** Airport Delays (FAA ASWS), Travel Advisories (RSS), NASA FIRMS Fires

---

## Task 1: NGA Maritime Safety Warnings

Adds real-time navigational warnings (NAVAREA, HYDROLANT/HYDROPAC) from the US DoD. Directly enriches our ship tracking with hazard awareness.

**Files:**
- Create: `collectors/nga_warnings.py`
- Modify: `main.py` (register collector + REST endpoint)
- Modify: `config.py` (add NGA URL + interval)
- Modify: `templates/dashboard.html` (add warnings panel to Map tab)
- Modify: `static/js/dashboard.js` (render warnings + map markers)

**API:** `GET https://msi.gs.mil/api/publications/broadcast-warn` — no auth, returns JSON

**Step 1: Add config**

In `config.py`, add:
```python
NGA_MSI_URL = "https://msi.gs.mil/api/publications/broadcast-warn"
NGA_POLL_INTERVAL = 1800  # 30 min
```

**Step 2: Create collector**

`collectors/nga_warnings.py` — extends `BaseCollector`, fetches NGA warnings, normalizes to `{id, title, type, area, date, lat, lon, text}`. Filter to active warnings only. Parse geographic coordinates from warning text where available.

**Step 3: Register in main.py**

Add collector startup, REST endpoint `GET /api/nga-warnings`, and WebSocket broadcast as module `nga_warnings`.

**Step 4: Add map markers**

Warning locations rendered as orange triangle markers on the Leaflet map with popup showing warning text. Add layer toggle button.

**Step 5: Commit**

```bash
git add collectors/nga_warnings.py main.py config.py templates/dashboard.html static/js/dashboard.js
git commit -m "feat: add NGA maritime safety warnings"
```

---

## Task 2: USGS Earthquake Monitoring

Adds global earthquake feed (M4.5+) as a new data layer on the map and a summary in a new "Natural Events" section.

**Files:**
- Create: `collectors/earthquakes.py`
- Modify: `main.py` (register collector + REST endpoint)
- Modify: `config.py` (add USGS URL + interval)
- Modify: `templates/dashboard.html` (earthquake indicators)
- Modify: `static/js/dashboard.js` (map layer + panel)

**API:** `GET https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/4.5_day.geojson` — no auth, GeoJSON, updated every 5 min by USGS

**Step 1: Add config**

```python
USGS_EARTHQUAKE_URL = "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/4.5_day.geojson"
USGS_POLL_INTERVAL = 300  # 5 min
```

**Step 2: Create collector**

`collectors/earthquakes.py` — fetches GeoJSON, extracts `{id, title, magnitude, lat, lon, depth, time, url, place}`. Broadcasts as module `earthquakes`.

**Step 3: Register and add endpoint**

REST endpoint `GET /api/earthquakes`, WebSocket module `earthquakes`.

**Step 4: Add map layer**

Earthquake markers as pulsing circles sized by magnitude, colored by depth. Red >= M6, orange >= M5, yellow >= M4.5. Add to layer toggle.

**Step 5: Commit**

```bash
git add collectors/earthquakes.py main.py config.py templates/dashboard.html static/js/dashboard.js
git commit -m "feat: add USGS earthquake monitoring"
```

---

## Task 3: Additional Cyber Threat Feeds

Add URLhaus (malware URLs) and C2IntelFeeds (community C2 indicators) to the existing cyber collector, matching World Monitor's 5-source aggregation.

**Files:**
- Modify: `collectors/cyber.py` (add two new feed fetchers)
- Modify: `config.py` (add feed URLs)

**APIs:**
- URLhaus: `GET https://urlhaus.abuse.ch/downloads/csv_recent/` — CSV, no auth
- C2IntelFeeds: `GET https://raw.githubusercontent.com/drb-ra/C2IntelFeeds/master/feeds/IPC2s-30day.csv` — CSV, no auth

**Step 1: Add URLs to config**

```python
URLHAUS_CSV_URL = "https://urlhaus.abuse.ch/downloads/csv_recent/"
C2INTEL_CSV_URL = "https://raw.githubusercontent.com/drb-ra/C2IntelFeeds/master/feeds/IPC2s-30day.csv"
```

**Step 2: Add fetchers in cyber.py**

Add `_fetch_urlhaus()` and `_fetch_c2intel()` methods. Parse CSV, normalize to existing `ThreatEvent` format with types `malware_url` and `c2_community`. Merge into existing `events` list during `collect()`.

**Step 3: Update stats calculation**

Include new source counts in the stats bar (total IOCs should now reflect all 5 sources).

**Step 4: Commit**

```bash
git add collectors/cyber.py config.py
git commit -m "feat: add URLhaus and C2IntelFeeds cyber sources"
```

---

## Task 4: Static Trade Routes & Strategic Chokepoints

Add 19 global trade routes and 6 strategic chokepoints as a static map layer. No API needed — embedded JSON data. This adds significant strategic context to the map.

**Files:**
- Create: `static/data/trade_routes.json` (route definitions with waypoints)
- Create: `static/data/chokepoints.json` (6 chokepoints with coordinates + metadata)
- Modify: `main.py` (serve static data endpoint)
- Modify: `static/js/dashboard.js` (render polylines + chokepoint markers on map)
- Modify: `templates/dashboard.html` (layer toggle)

**Step 1: Create trade_routes.json**

Define 19 routes as arrays of `[lat, lon]` waypoints with metadata: `{name, type: "container"|"energy"|"bulk", waypoints: [[lat,lon]...]}`. Key routes: Suez-Mediterranean, Malacca-East Asia, Hormuz-Indian Ocean, Panama-Atlantic, Cape of Good Hope.

**Step 2: Create chokepoints.json**

6 chokepoints: `{name, lat, lon, daily_traffic, strategic_importance, description}` — Suez Canal, Strait of Malacca, Strait of Hormuz, Bab el-Mandeb, Panama Canal, Taiwan Strait.

**Step 3: Add map rendering**

Trade routes as dashed polylines (blue for container, red for energy, brown for bulk). Chokepoints as diamond markers with info popup showing traffic volume and importance.

**Step 4: Add layer toggle**

New "Trade Routes" toggle button in the map controls.

**Step 5: Commit**

```bash
git add static/data/ main.py static/js/dashboard.js templates/dashboard.html
git commit -m "feat: add trade routes and chokepoint map layer"
```

---

## Task 5: GDELT Geo-Events Integration

Enriches the news heatmap with GDELT's event-level geolocation data, providing much denser geographic coverage than our 5 RSS sources alone.

**Files:**
- Create: `collectors/gdelt.py`
- Modify: `main.py` (register collector + REST endpoint)
- Modify: `config.py` (add GDELT URL + interval)
- Modify: `static/js/dashboard.js` (merge GDELT events into heatmap)

**API:** `GET https://api.gdeltproject.org/api/v2/geo/geo?query=conflict+OR+military+OR+crisis&format=GeoJSON` — no auth

**Step 1: Add config**

```python
GDELT_GEO_URL = "https://api.gdeltproject.org/api/v2/geo/geo"
GDELT_POLL_INTERVAL = 600  # 10 min
```

**Step 2: Create collector**

`collectors/gdelt.py` — queries GDELT GEO 2.0 API with conflict/military/crisis keywords. Extracts `{lat, lon, name, url, tone, source}` from GeoJSON features. Broadcasts as module `gdelt`.

**Step 3: Register endpoint**

REST endpoint `GET /api/gdelt`, WebSocket module `gdelt`.

**Step 4: Merge into heatmap**

GDELT geo-events added as additional heat points on the existing news heatmap layer, weighted by GDELT tone score (more negative = higher heat).

**Step 5: Commit**

```bash
git add collectors/gdelt.py main.py config.py static/js/dashboard.js
git commit -m "feat: add GDELT geo-event heatmap enrichment"
```

---

## Task 6: GPS/GNSS Jamming Zones (from gpsjam.org)

Visualizes GPS interference detected from ADS-B transponder anomalies. High value for military situational awareness in conflict zones.

**Files:**
- Create: `collectors/gps_jamming.py`
- Modify: `main.py` (register collector + REST endpoint)
- Modify: `config.py` (add URL + interval)
- Modify: `static/js/dashboard.js` (render jamming zones on map)

**API:** Scrape/fetch from `https://gpsjam.org` — public data derived from ADS-B Exchange. Need to inspect their data format (likely GeoJSON or tile-based).

**Step 1: Research gpsjam.org data format**

Inspect the site to determine if they expose a JSON/GeoJSON API or if we need to scrape. Document findings before implementing.

**Step 2: Create collector**

`collectors/gps_jamming.py` — fetches interference data, normalizes to H3 hex cells or simple `{lat, lon, interference_pct, level: "medium"|"high"}`. Filter out cells with < 3 aircraft (noise). Poll every 30 min.

**Step 3: Render on map**

Amber circles for medium interference (2-10%), red circles for high (>10%). Add layer toggle "GPS Jamming".

**Step 4: Commit**

```bash
git add collectors/gps_jamming.py main.py config.py static/js/dashboard.js
git commit -m "feat: add GPS/GNSS jamming zone visualization"
```

---

## Task 7: Strategic Ports Layer

Add 83 strategic ports as a static map layer, categorized by type. Complements trade routes and ship tracking.

**Files:**
- Create: `static/data/strategic_ports.json`
- Modify: `static/js/dashboard.js` (render port markers)
- Modify: `templates/dashboard.html` (layer toggle)

**Step 1: Create port data**

JSON array of `{name, lat, lon, country, type: "container"|"oil_lng"|"naval"|"chokepoint"|"mixed"|"bulk", throughput_rank, description}`. Focus on top 50 ports initially.

**Step 2: Render on map**

Ports as small square markers, color-coded by type: blue (container), red (oil/LNG), green (naval), purple (mixed). Show on zoom level >= 4 only to avoid clutter.

**Step 3: Commit**

```bash
git add static/data/strategic_ports.json static/js/dashboard.js templates/dashboard.html
git commit -m "feat: add strategic ports map layer"
```

---

## Implementation Order

1. **Task 3** (Cyber feeds) — smallest change, modifies existing collector only
2. **Task 4** (Trade routes) — static data, no collector needed, high visual impact
3. **Task 7** (Strategic ports) — static data, complements trade routes
4. **Task 1** (NGA warnings) — new collector, enriches ship tracking
5. **Task 2** (USGS earthquakes) — new collector, new data domain
6. **Task 5** (GDELT) — new collector, enriches existing heatmap
7. **Task 6** (GPS jamming) — requires research on data availability first

---

## Out of Scope (Future Consideration)

These require API keys or more complex integration:
- **ACLED conflict data** — free researcher account needed
- **Finnhub / FRED / EIA** — free keys, would significantly expand markets module
- **NASA FIRMS fires** — free key from EOSDIS
- **Cloudflare Radar outages** — enterprise only
- **Wingbits ADS-B** — commercial/paid
- **FAA ASWS airport delays** — free but US-only
- **Travel advisories** — RSS feeds from US/UK/AU/NZ governments
- **Telegram OSINT feed** — requires Telegram API credentials + relay server
- **3D Globe** — major frontend rewrite (globe.gl + Three.js)
