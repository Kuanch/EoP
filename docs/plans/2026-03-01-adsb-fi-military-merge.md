# Merge adsb.fi Military Data with OpenSky Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Merge adsb.fi military aircraft data with existing OpenSky data to improve aircraft coverage, especially in the Middle East.

**Architecture:** Add adsb.fi as a second data source in `MilitaryCollector`. Each `collect()` cycle fetches from both OpenSky (per-region bbox queries) and adsb.fi (`/v2/mil` global military endpoint). Results are merged and deduplicated by ICAO24 hex code, with adsb.fi taking priority when duplicates exist (it has richer metadata). No new files needed — this modifies the existing collector and config.

**Tech Stack:** Python, httpx (async HTTP), existing BaseCollector pattern

---

### Task 1: Add adsb.fi config constants

**Files:**
- Modify: `config.py:63` (near OpenSky config)

**Step 1: Add adsb.fi constants to config.py**

Add these lines after `OPENSKY_API_URL` (line 63):

```python
# adsb.fi Open Data API (free, no auth required)
ADSBFI_MIL_URL = "https://opendata.adsb.fi/api/v2/mil"
```

**Step 2: Commit**

```bash
git add config.py
git commit -m "feat: add adsb.fi API config constant"
```

---

### Task 2: Add adsb.fi fetch method to MilitaryCollector

**Files:**
- Modify: `collectors/military.py`

**Step 1: Add import of new config constant**

In `collectors/military.py`, update the import on line 12-14 to include `ADSBFI_MIL_URL`:

```python
from config import (
    MILITARY_POLL_INTERVAL, MILITARY_BROADCAST_INTERVAL, OPENSKY_API_URL,
    MONITORED_REGIONS, HTTP_TIMEOUT, ADSBFI_MIL_URL,
)
```

**Step 2: Add `_fetch_adsbfi` method to `MilitaryCollector`**

Add this method after `_get_token` (after line 78):

```python
async def _fetch_adsbfi(self, client: httpx.AsyncClient) -> list[dict]:
    """Fetch military aircraft from adsb.fi global military endpoint."""
    try:
        resp = await client.get(ADSBFI_MIL_URL, timeout=HTTP_TIMEOUT)
        if resp.status_code == 200:
            data = resp.json()
            aircraft_list = data.get("ac", [])
            assets = []
            for ac in aircraft_list:
                lat = ac.get("lat")
                lon = ac.get("lon")
                if lat is None or lon is None:
                    continue
                # Check if aircraft is on ground
                alt_baro = ac.get("alt_baro")
                if alt_baro == "ground":
                    continue
                # Determine which monitored region this aircraft is in
                region = self._find_region(lat, lon)
                if not region:
                    continue
                callsign = (ac.get("flight") or "").strip()
                alt = ac.get("alt_geom") or (alt_baro if isinstance(alt_baro, (int, float)) else None)
                # Convert feet to meters to match OpenSky format
                alt_meters = round(alt * 0.3048, 0) if alt else None
                heading = ac.get("track")
                assets.append({
                    "callsign": callsign,
                    "type": "aircraft",
                    "lat": lat,
                    "lon": lon,
                    "altitude": alt_meters,
                    "heading": round(heading, 0) if heading else None,
                    "region": region,
                    "source": "adsb.fi",
                    "icao24": ac.get("hex", "").lower(),
                    "origin_country": ac.get("ownOp") or ac.get("r") or "",
                })
            logger.info(f"[military] adsb.fi returned {len(assets)} military aircraft in monitored regions")
            return assets
        else:
            logger.warning(f"[military] adsb.fi: {resp.status_code}")
    except Exception as e:
        logger.error(f"[military] adsb.fi error: {e}")
    return []
```

**Step 3: Add `_find_region` helper method**

Add this static helper method right after `_fetch_adsbfi`:

```python
@staticmethod
def _find_region(lat: float, lon: float) -> str | None:
    """Return the name of the monitored region containing this lat/lon, or None."""
    for name, info in MONITORED_REGIONS.items():
        bbox = info["bbox"]
        if bbox[0] <= lat <= bbox[1] and bbox[2] <= lon <= bbox[3]:
            return name
    return None
```

**Step 4: Commit**

```bash
git add collectors/military.py
git commit -m "feat: add adsb.fi military aircraft fetch method"
```

---

### Task 3: Merge both sources in collect() with deduplication

**Files:**
- Modify: `collectors/military.py` — the `collect()` method (lines 95-154)

**Step 1: Update `collect()` to fetch from both sources and merge**

Replace the `collect` method with:

```python
async def collect(self):
    all_assets = []

    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
        # Fetch from both sources concurrently
        opensky_task = asyncio.create_task(self._fetch_opensky(client))
        adsbfi_task = asyncio.create_task(self._fetch_adsbfi(client))

        opensky_assets = await opensky_task
        adsbfi_assets = await adsbfi_task

        # Merge: deduplicate by icao24, adsb.fi takes priority (richer metadata)
        seen = {}
        for asset in adsbfi_assets:
            icao = asset.get("icao24", "").lower()
            if icao:
                seen[icao] = asset
        for asset in opensky_assets:
            icao = asset.get("icao24", "").lower()
            if icao and icao not in seen:
                seen[icao] = asset
        all_assets = list(seen.values())

    assets_cache.clear()
    assets_cache.extend(all_assets)
    await manager.broadcast("military", all_assets)
    logger.info(f"[military] Tracking {len(all_assets)} assets across {len(MONITORED_REGIONS)} regions (OpenSky: {len(opensky_assets)}, adsb.fi: {len(adsbfi_assets)})")
    return all_assets
```

**Step 2: Extract existing OpenSky logic into `_fetch_opensky` method**

Move the current OpenSky fetch logic from `collect()` into a new method:

```python
async def _fetch_opensky(self, client: httpx.AsyncClient) -> list[dict]:
    """Fetch aircraft from OpenSky Network per-region bounding boxes."""
    assets = []
    token = await self._get_token(client)
    headers = {"Authorization": f"Bearer {token}"} if token else {}

    for i, (region_name, region_info) in enumerate(MONITORED_REGIONS.items()):
        if i > 0:
            await asyncio.sleep(5)
        bbox = region_info["bbox"]
        params = {
            "lamin": bbox[0], "lamax": bbox[1],
            "lomin": bbox[2], "lomax": bbox[3],
        }
        try:
            resp = await client.get(OPENSKY_API_URL, params=params, headers=headers)
            if resp.status_code == 429:
                logger.warning(f"[military] OpenSky rate limited for {region_name}, retrying in 10s")
                await asyncio.sleep(10)
                resp = await client.get(OPENSKY_API_URL, params=params, headers=headers)
            if resp.status_code == 200:
                data = resp.json()
                states = data.get("states", []) or []
                for s in states:
                    if len(s) < 12:
                        continue
                    callsign = (s[1] or "").strip()
                    lat = s[6]
                    lon = s[5]
                    alt = s[7] or s[13]
                    heading = s[10]
                    on_ground = s[8]

                    if on_ground:
                        continue

                    assets.append({
                        "callsign": callsign,
                        "type": "aircraft",
                        "lat": lat,
                        "lon": lon,
                        "altitude": round(alt, 0) if alt else None,
                        "heading": round(heading, 0) if heading else None,
                        "region": region_name,
                        "source": "OpenSky",
                        "icao24": s[0],
                        "origin_country": s[2],
                    })
            else:
                logger.warning(f"[military] OpenSky {region_name}: {resp.status_code}")
        except Exception as e:
            logger.error(f"[military] OpenSky {region_name}: {e}")
    return assets
```

**Step 3: Commit**

```bash
git add collectors/military.py
git commit -m "feat: merge OpenSky + adsb.fi sources with icao24 deduplication"
```

---

### Task 4: Verify end-to-end

**Step 1: Restart the server and check logs**

```bash
# Kill existing server, restart
pkill -f "uvicorn main:app" ; sleep 1
venv/bin/uvicorn main:app --host 0.0.0.0 --port 8000 &
sleep 10
# Check logs for both sources reporting
grep -i "military" server.log | tail -10
```

Expected: Log lines showing both `adsb.fi returned X military aircraft` and `Tracking N assets ... (OpenSky: X, adsb.fi: Y)`

**Step 2: Check API response**

```bash
curl -s http://localhost:8000/api/military | python3 -c "
import sys, json
data = json.load(sys.stdin)
sources = {}
for a in data:
    s = a.get('source','?')
    sources[s] = sources.get(s,0) + 1
print(sources)
"
```

Expected: `{'OpenSky': X, 'adsb.fi': Y}` — both sources present.

**Step 3: Commit any fixes if needed, then final commit**

```bash
git add -A
git commit -m "feat: complete adsb.fi + OpenSky military aircraft merge"
```
