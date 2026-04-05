# Signal Monitor: 24h Window + 7-Day Moving Average

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Extend the IODA signal monitor from a 6-hour window to 24 hours, and add a 7-day global moving average baseline so sustained multi-day degradation is detectable.

**Architecture:** Fetch 24h of signal data per cycle (maxPoints=48, 30-min resolution). Cache daily averages to a JSON file on disk (following `markets.py` pattern). Compute two metrics: `pct_change_24h` (current vs 24h average) and `pct_change_7d` (current vs 7-day MA). Status classification uses the worse of both windows. Frontend gets both metrics for display.

**Tech Stack:** Python (httpx, json), existing `data/` persistence directory, Leaflet.js frontend

---

### Task 1: Add config constants for new signal parameters

**Files:**
- Modify: `config.py:84-88`

**Step 1: Add signal lookback and max points constants**

In `config.py`, after the existing IODA config block, replace/add:

```python
IODA_SIGNAL_LOOKBACK = 86400       # 24 hours of signal data
IODA_SIGNAL_MAX_POINTS = 48        # 30-min resolution over 24h
```

**Step 2: Verify no import errors**

Run: `cd /home/sixigma/EoP && venv/bin/python -c "from config import IODA_SIGNAL_LOOKBACK, IODA_SIGNAL_MAX_POINTS; print('OK')"`
Expected: `OK`

**Step 3: Commit**

```bash
git add config.py
git commit -m "config: add IODA signal lookback and max points constants"
```

---

### Task 2: Add disk persistence for signal history

**Files:**
- Modify: `collectors/cyber.py` (top-level, before class)

**Step 1: Add signal history file path and load/save functions**

Add after the `cyber_events_legacy` line (~line 37), following the `markets.py` pattern:

```python
SIGNAL_HISTORY_FILE = "data/signal_history.json"


def _load_signal_history() -> dict:
    """Load persistent signal daily averages from disk.
    
    Structure: {country_code: {datasource: [{date: "YYYY-MM-DD", avg: float}, ...]}}
    Keeps last 8 days (7-day window + today's partial).
    """
    if not os.path.exists(SIGNAL_HISTORY_FILE):
        return {}
    try:
        with open(SIGNAL_HISTORY_FILE, "r") as f:
            data = json.load(f)
        # Prune entries older than 8 days
        cutoff = (datetime.utcnow() - timedelta(days=8)).strftime("%Y-%m-%d")
        for code in data:
            for ds in data[code]:
                data[code][ds] = [e for e in data[code][ds] if e["date"] >= cutoff]
        return data
    except Exception as e:
        logger.error(f"[cyber] Failed to load signal history: {e}")
        return {}


def _save_signal_history(history: dict):
    """Save signal daily averages to disk."""
    try:
        os.makedirs(os.path.dirname(SIGNAL_HISTORY_FILE), exist_ok=True)
        with open(SIGNAL_HISTORY_FILE, "w") as f:
            json.dump(history, f)
    except Exception as e:
        logger.error(f"[cyber] Failed to save signal history: {e}")
```

**Step 2: Add missing imports**

At top of `cyber.py`, ensure `os` and `timedelta` are imported:

```python
import os
from datetime import datetime, timedelta
```

(Note: `datetime` is already imported, just add `timedelta` and `os`)

**Step 3: Verify no import errors**

Run: `cd /home/sixigma/EoP && venv/bin/python -c "from collectors.cyber import _load_signal_history, _save_signal_history; print('OK')"`
Expected: `OK`

**Step 4: Commit**

```bash
git add collectors/cyber.py
git commit -m "feat(cyber): add disk persistence for signal history"
```

---

### Task 3: Rewrite `_fetch_watched_signals` for 24h window + 7d baseline

**Files:**
- Modify: `collectors/cyber.py:170-249` (`_fetch_watched_signals` method)

**Step 1: Update the method to use new config constants and compute dual metrics**

Replace the entire `_fetch_watched_signals` method with:

```python
async def _fetch_watched_signals(self, client: httpx.AsyncClient) -> dict:
    """Fetch real-time signal levels for watched countries.

    Returns {country_code: {datasource: {values, pct_change_24h, pct_change_7d, status}}}
    Uses 24h window for trend visualization and 7-day MA for sustained anomaly detection.
    Watched countries also appear in outage events/alerts — both sources
    together give a more complete threat picture.
    """
    now = int(time.time())
    signals: dict[str, dict] = {}
    signal_history = _load_signal_history()
    today = datetime.utcnow().strftime("%Y-%m-%d")

    for code in IODA_WATCHED_COUNTRIES:
        if code not in COUNTRY_GEO:
            continue
        geo = COUNTRY_GEO[code]
        signals[code] = {"name": geo["name"], "lat": geo["lat"], "lon": geo["lon"],
                         "region": geo["region"], "datasources": {}}

        if code not in signal_history:
            signal_history[code] = {}

        for ds in IODA_SIGNAL_DATASOURCES:
            try:
                resp = await client.get(
                    f"{IODA_API_BASE}/signals/raw/country/{code}",
                    params={
                        "datasource": ds,
                        "from": now - IODA_SIGNAL_LOOKBACK,
                        "until": now,
                        "maxPoints": IODA_SIGNAL_MAX_POINTS,
                    },
                )
                if resp.status_code != 200:
                    continue
                data = resp.json().get("data", [])
                if not data:
                    continue

                # API returns nested list: [[{entity_dict}]]
                inner = data[0] if isinstance(data, list) and data else data
                entry = inner[0] if isinstance(inner, list) and inner else inner
                if not isinstance(entry, dict):
                    logger.warning(f"[cyber] Signal {code}/{ds}: unexpected response shape")
                    continue
                values = entry.get("values", [])
                if not values or not any(v is not None for v in values):
                    continue

                # Filter out None values
                valid = [v for v in values if v is not None]
                if len(valid) < 2:
                    signals[code]["datasources"][ds] = {
                        "current": valid[-1] if valid else 0,
                        "pct_change_24h": 0,
                        "pct_change_7d": 0,
                        "status": "unknown",
                        "values": values,
                    }
                    continue

                current = valid[-1]
                baseline_24h = sum(valid[:-1]) / len(valid[:-1])

                if baseline_24h == 0:
                    pct_24h = 0.0
                else:
                    pct_24h = round((current - baseline_24h) / baseline_24h * 100, 1)

                # Update today's daily average in history
                daily_avg = sum(valid) / len(valid)
                if ds not in signal_history[code]:
                    signal_history[code][ds] = []
                history_entries = signal_history[code][ds]
                # Replace today's entry if exists, otherwise append
                history_entries = [e for e in history_entries if e["date"] != today]
                history_entries.append({"date": today, "avg": round(daily_avg, 2)})
                signal_history[code][ds] = history_entries

                # Compute 7-day MA (exclude today's partial)
                past_entries = [e for e in history_entries if e["date"] != today]
                if past_entries:
                    baseline_7d = sum(e["avg"] for e in past_entries) / len(past_entries)
                    pct_7d = round((current - baseline_7d) / baseline_7d * 100, 1) if baseline_7d else 0.0
                else:
                    baseline_7d = baseline_24h  # Bootstrap: no history yet
                    pct_7d = pct_24h

                # Classify health — use worse of both windows
                worst_pct = min(pct_24h, pct_7d)
                if worst_pct < -30:
                    status = "critical"
                elif worst_pct < -15:
                    status = "degraded"
                elif worst_pct < -5:
                    status = "warning"
                else:
                    status = "normal"

                signals[code]["datasources"][ds] = {
                    "current": round(current, 1),
                    "baseline_24h": round(baseline_24h, 1),
                    "baseline_7d": round(baseline_7d, 1),
                    "pct_change_24h": pct_24h,
                    "pct_change_7d": pct_7d,
                    "status": status,
                    "values": [round(v, 1) if v is not None else None for v in values],
                }
            except Exception as e:
                logger.error(f"[cyber] Signal {code}/{ds}: {e}")

    _save_signal_history(signal_history)
    return signals
```

**Step 2: Add config imports**

Update the import line in `cyber.py`:

```python
from config import (
    CYBER_POLL_INTERVAL, CISA_KEV_URL,
    IODA_API_BASE, IODA_ALERT_LOOKBACK, IODA_EVENT_LOOKBACK,
    IODA_WATCHED_COUNTRIES, IODA_SIGNAL_DATASOURCES,
    IODA_SIGNAL_LOOKBACK, IODA_SIGNAL_MAX_POINTS,
    CYBER_NEWS_FEEDS, HTTP_TIMEOUT, HTTP_USER_AGENT,
)
```

**Step 3: Verify no import errors**

Run: `cd /home/sixigma/EoP && venv/bin/python -c "from collectors.cyber import CyberCollector; print('OK')"`
Expected: `OK`

**Step 4: Commit**

```bash
git add collectors/cyber.py
git commit -m "feat(cyber): extend signal monitor to 24h window with 7-day MA baseline"
```

---

### Task 4: Update frontend to display dual metrics

**Files:**
- Modify: `static/js/cyber.js` (renderWatchedSignals + renderWatchedPanel)
- Modify: `templates/base.html` (cache bust)

**Step 1: Update tooltip in `renderWatchedSignals()`**

The tooltip currently shows `d.pct_change`. Update to show both:
- Change references from `d.pct_change` to `d.pct_change_24h`
- Add a second line showing `d.pct_change_7d` labeled as "7d"

In the tooltip builder (~line 244-253), replace the datasource loop body:

```javascript
Object.entries(info.datasources).forEach(([ds, d]) => {
    const dsColor = this._statusColor(d.status);
    const arrow24 = d.pct_change_24h > 0 ? '▲' : d.pct_change_24h < 0 ? '▼' : '—';
    const arrow7d = d.pct_change_7d > 0 ? '▲' : d.pct_change_7d < 0 ? '▼' : '—';
    const spark = this._miniSparkline(d.values, dsColor, 60, 18);
    tip += `<div style="margin-top:4px;">` +
        `<span style="color:${dsColor};font-weight:600;">${this.esc(this._datasourceLabel(ds))}</span> ` +
        `${spark} ` +
        `<span style="color:${dsColor};">${arrow24} ${d.pct_change_24h > 0 ? '+' : ''}${d.pct_change_24h}% 24h</span>` +
        `<span style="color:var(--text-secondary);font-size:11px;"> | ${arrow7d} ${d.pct_change_7d > 0 ? '+' : ''}${d.pct_change_7d}% 7d</span>` +
        `</div>`;
});
```

**Step 2: Update `renderWatchedPanel()` datasource rows**

In the panel (~line 278-287), replace the datasource row builder:

```javascript
const dsHtml = Object.entries(info.datasources).map(([ds, d]) => {
    const c = this._statusColor(d.status);
    const arrow24 = d.pct_change_24h > 0 ? '▲' : d.pct_change_24h < 0 ? '▼' : '—';
    const arrow7d = d.pct_change_7d > 0 ? '▲' : d.pct_change_7d < 0 ? '▼' : '—';
    const spark = this._miniSparkline(d.values, c, 80, 20);
    return `<div style="display:flex;align-items:center;gap:8px;margin-top:4px;">` +
        `<span style="font-size:12px;color:${c};font-weight:600;min-width:110px;">${this.esc(this._datasourceLabel(ds))}</span>` +
        `${spark}` +
        `<span style="font-size:12px;color:${c};">${arrow24} ${d.pct_change_24h > 0 ? '+' : ''}${d.pct_change_24h}%</span>` +
        `<span style="font-size:11px;color:var(--text-secondary);">24h</span>` +
        `<span style="font-size:12px;color:${c};margin-left:4px;">${arrow7d} ${d.pct_change_7d > 0 ? '+' : ''}${d.pct_change_7d}%</span>` +
        `<span style="font-size:11px;color:var(--text-secondary);">7d</span>` +
        `</div>`;
}).join('');
```

**Step 3: Cache bust**

In `templates/base.html`, bump `cyber.js?v=5` to `cyber.js?v=6`.

**Step 4: Verify the server starts without errors**

Restart the server and check logs for the cyber collector output. It should now show `pct_change_24h` and `pct_change_7d` in the signal data.

**Step 5: Commit**

```bash
git add static/js/cyber.js templates/base.html
git commit -m "ui(cyber): show 24h and 7-day signal change in watched panel and tooltips"
```

---

### Task 5: Backfill 7-day history on first startup

**Files:**
- Modify: `collectors/cyber.py` (add `_backfill_signal_history` method to class)

**Step 1: Add a one-time backfill method**

Add this method to `CyberCollector`, called once on first `collect()` if history file is empty:

```python
async def _backfill_signal_history(self, client: httpx.AsyncClient):
    """One-time backfill: fetch 7 days of daily signal averages for watched countries."""
    history = _load_signal_history()
    if any(history.get(c, {}).get(ds) for c in IODA_WATCHED_COUNTRIES for ds in IODA_SIGNAL_DATASOURCES):
        return  # Already have some history, skip backfill

    logger.info("[cyber] Backfilling 7-day signal history...")
    now = int(time.time())

    for code in IODA_WATCHED_COUNTRIES:
        if code not in COUNTRY_GEO:
            continue
        if code not in history:
            history[code] = {}

        for ds in IODA_SIGNAL_DATASOURCES:
            try:
                # Fetch 7 days with 1 point per day
                resp = await client.get(
                    f"{IODA_API_BASE}/signals/raw/country/{code}",
                    params={
                        "datasource": ds,
                        "from": now - 7 * 86400,
                        "until": now,
                        "maxPoints": 7,
                    },
                )
                if resp.status_code != 200:
                    continue
                data = resp.json().get("data", [])
                if not data:
                    continue

                inner = data[0] if isinstance(data, list) and data else data
                entry = inner[0] if isinstance(inner, list) and inner else inner
                if not isinstance(entry, dict):
                    continue

                values = entry.get("values", [])
                valid = [v for v in values if v is not None]
                if not valid:
                    continue

                # Create daily entries for the past 7 days
                entries = []
                for i, val in enumerate(valid):
                    day = datetime.utcfromtimestamp(now - (7 - i) * 86400).strftime("%Y-%m-%d")
                    entries.append({"date": day, "avg": round(val, 2)})

                history[code][ds] = entries
                logger.info(f"[cyber] Backfilled {code}/{ds}: {len(entries)} days")
            except Exception as e:
                logger.error(f"[cyber] Backfill {code}/{ds}: {e}")

    _save_signal_history(history)
```

**Step 2: Call backfill at the start of `collect()`**

In the `collect()` method, right after the `async with httpx.AsyncClient(...)` line, add:

```python
# One-time backfill of 7-day history on first run
await self._backfill_signal_history(client)
```

**Step 3: Verify no import errors**

Run: `cd /home/sixigma/EoP && venv/bin/python -c "from collectors.cyber import CyberCollector; print('OK')"`
Expected: `OK`

**Step 4: Commit**

```bash
git add collectors/cyber.py
git commit -m "feat(cyber): backfill 7-day signal history on first startup"
```

---

### Task 6: Verify end-to-end and push

**Step 1: Delete any existing history file to test backfill**

```bash
rm -f /home/sixigma/EoP/data/signal_history.json
```

**Step 2: Restart the server**

Kill existing process and start fresh. Watch logs for:
- `[cyber] Backfilling 7-day signal history...`
- `[cyber] Backfilled TW/merit-nt: 7 days`
- `[cyber] Backfilled TW/bgp: 7 days`
- (same for UA and IR)
- `[cyber] X outages, Y articles, Z CVEs, ... 3 watched (6 signals)`

**Step 3: Verify the history file was created**

```bash
cat /home/sixigma/EoP/data/signal_history.json | python3 -m json.tool | head -30
```

Should show 7 daily entries per country/datasource.

**Step 4: Verify frontend via WebSocket data**

Check that watched signal data now includes `pct_change_24h`, `pct_change_7d`, `baseline_24h`, `baseline_7d` fields.

**Step 5: Push all commits**

```bash
git push
```
