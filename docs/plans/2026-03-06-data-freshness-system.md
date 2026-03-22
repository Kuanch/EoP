# Data Freshness & Upstream Health System

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a data freshness registry that tracks every collector's health (last success, last error, staleness) with a REST endpoint and UI badges, so users never mistake "source is down" for "the world is quiet."

**Architecture:** A singleton `DataFreshnessTracker` in `collectors/freshness.py` stores per-source timestamps and status. `BaseCollector` auto-reports success/failure after each `collect()` cycle. A new `GET /api/health/data` endpoint exposes the registry. The navbar gets colored dots per module showing fresh/stale/down status.

**Tech Stack:** Python (dataclass registry), FastAPI (REST endpoint), vanilla JS (UI badges)

---

### Task 1: Create the DataFreshnessTracker singleton

**Files:**
- Create: `collectors/freshness.py`

**Step 1: Write the tracker module**

```python
"""Data freshness tracker — singleton registry for collector health."""

import time
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class SourceStatus:
    name: str
    last_success: float = 0.0
    last_error: float = 0.0
    last_error_msg: str = ""
    collect_count: int = 0
    error_count: int = 0

    @property
    def age_seconds(self) -> float:
        if self.last_success == 0:
            return float("inf")
        return time.time() - self.last_success

    @property
    def status(self) -> str:
        age = self.age_seconds
        if age == float("inf"):
            if self.last_error > 0:
                return "error"
            return "no_data"
        if age < self._stale_threshold:
            return "fresh"
        if age < self._stale_threshold * 4:
            return "stale"
        return "down"

    @property
    def _stale_threshold(self) -> float:
        """2x the expected interval is considered stale."""
        return _INTERVALS.get(self.name, 600)


# Expected poll intervals per source (seconds) — used for staleness classification
_INTERVALS: dict[str, float] = {}


class DataFreshnessTracker:
    """Singleton tracker for all data source health."""

    _instance: Optional["DataFreshnessTracker"] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._sources: dict[str, SourceStatus] = {}
        return cls._instance

    def register(self, name: str, interval: float):
        """Register a source with its expected poll interval."""
        _INTERVALS[name] = interval * 2  # stale after 2x interval
        if name not in self._sources:
            self._sources[name] = SourceStatus(name=name)

    def report_success(self, name: str):
        src = self._sources.get(name)
        if src:
            src.last_success = time.time()
            src.collect_count += 1

    def report_error(self, name: str, error: str):
        src = self._sources.get(name)
        if src:
            src.last_error = time.time()
            src.last_error_msg = str(error)[:200]
            src.error_count += 1

    def snapshot(self) -> dict:
        """Return JSON-serializable health snapshot."""
        now = time.time()
        result = {}
        for name, src in self._sources.items():
            age = src.age_seconds
            result[name] = {
                "status": src.status,
                "last_success_ago": round(age, 1) if age != float("inf") else None,
                "last_error_msg": src.last_error_msg or None,
                "collect_count": src.collect_count,
                "error_count": src.error_count,
            }
        return result


# Module-level convenience
tracker = DataFreshnessTracker()
```

**Step 2: Commit**

```bash
git add collectors/freshness.py
git commit -m "feat: add DataFreshnessTracker singleton for collector health"
```

---

### Task 2: Integrate tracker into BaseCollector

**Files:**
- Modify: `collectors/base.py`

**Step 1: Update BaseCollector to auto-report**

Replace the entire `collectors/base.py` with:

```python
"""Abstract base collector for all data sources."""

import asyncio
import logging
from abc import ABC, abstractmethod
from collectors.freshness import tracker

logger = logging.getLogger(__name__)


class BaseCollector(ABC):
    def __init__(self, name: str, interval: int):
        self.name = name
        self.interval = interval
        self._running = False
        tracker.register(name, interval)

    @abstractmethod
    async def collect(self) -> list | dict:
        """Collect data from the source. Must be implemented by subclasses."""
        ...

    async def run(self):
        """Main loop: collect, handle errors, sleep."""
        self._running = True
        logger.info(f"[{self.name}] collector started (interval={self.interval}s)")
        while self._running:
            try:
                await self.collect()
                tracker.report_success(self.name)
            except Exception as e:
                logger.error(f"[{self.name}] collection error: {e}")
                tracker.report_error(self.name, str(e))
            await asyncio.sleep(self.interval)

    def stop(self):
        self._running = False
```

Key change: `tracker.register()` in `__init__`, `tracker.report_success()` after successful `collect()`, `tracker.report_error()` in the except block.

**Step 2: Verify no import issues**

Run: `cd /home/sixigma/EoP && venv/bin/python3 -c "from collectors.base import BaseCollector; print('OK')"`
Expected: `OK`

**Step 3: Commit**

```bash
git add collectors/base.py
git commit -m "feat: integrate freshness tracker into BaseCollector"
```

---

### Task 3: Register the ShipCollector (non-BaseCollector)

The `ShipCollector` has its own run loop and doesn't extend `BaseCollector` the same way. Check `collectors/ships.py` for its structure and manually add tracker calls.

**Files:**
- Modify: `collectors/ships.py`

**Step 1: Read ships.py to find the collect/poll methods**

Find the main polling loop and add:
```python
from collectors.freshness import tracker

# In __init__ or at module level:
tracker.register("ships", 5)

# After successful broadcast:
tracker.report_success("ships")

# In error handler:
tracker.report_error("ships", str(e))
```

**Step 2: Commit**

```bash
git add collectors/ships.py
git commit -m "feat: add freshness tracking to ShipCollector"
```

---

### Task 4: Add REST endpoint GET /api/health/data

**Files:**
- Modify: `main.py`

**Step 1: Add the endpoint**

Add before the `# --- Background tasks ---` section in `main.py`:

```python
# --- Data Freshness ---

@app.get("/api/health/data")
@limiter.limit("60/minute")
async def health_data(request: Request):
    from collectors.freshness import tracker
    return JSONResponse(tracker.snapshot())
```

**Step 2: Test manually**

Run: `curl -s http://localhost:8000/api/health/data | python3 -m json.tool`
Expected: JSON object with keys like `news`, `markets`, `military`, `cyber`, `ships`, `pizzint`, `polymarket`, each with `status`, `last_success_ago`, etc.

**Step 3: Commit**

```bash
git add main.py
git commit -m "feat: add GET /api/health/data endpoint"
```

---

### Task 5: Add freshness badges to the navbar UI

**Files:**
- Modify: `templates/base.html` (add badge container)
- Modify: `static/js/ws.js` (poll health endpoint and update badges)
- Modify: `static/css/style.css` (badge styles)

**Step 1: Add badge HTML to navbar**

In `templates/base.html`, after the `<span id="ws-status"...>` element, add:

```html
<span id="data-health" class="data-health" title="Data source health">
    <span class="health-dot" data-source="news" title="News"></span>
    <span class="health-dot" data-source="markets" title="Markets"></span>
    <span class="health-dot" data-source="military" title="Military"></span>
    <span class="health-dot" data-source="cyber" title="Cyber"></span>
    <span class="health-dot" data-source="ships" title="Ships"></span>
    <span class="health-dot" data-source="pizzint" title="PizzINT"></span>
    <span class="health-dot" data-source="polymarket" title="Polymarket"></span>
</span>
```

**Step 2: Add CSS styles**

In `static/css/style.css`, add:

```css
/* Data freshness badges */
.data-health {
    display: inline-flex;
    gap: 4px;
    align-items: center;
    margin-right: 12px;
}
.health-dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: #555;
    display: inline-block;
    transition: background 0.3s;
    cursor: help;
}
.health-dot.fresh { background: #4caf50; }
.health-dot.stale { background: #ff9800; }
.health-dot.down, .health-dot.error { background: #f44336; }
.health-dot.no_data { background: #555; }
```

**Step 3: Add health polling in ws.js**

At the end of `ws.js`, add a polling function:

```javascript
// Data freshness polling
const DataHealth = {
    poll() {
        fetch('/api/health/data')
            .then(r => r.json())
            .then(data => {
                document.querySelectorAll('.health-dot').forEach(dot => {
                    const src = dot.dataset.source;
                    const info = data[src];
                    if (!info) return;
                    dot.className = 'health-dot ' + info.status;
                    const age = info.last_success_ago;
                    const ageText = age === null ? 'no data' :
                        age < 60 ? Math.round(age) + 's ago' :
                        age < 3600 ? Math.round(age / 60) + 'm ago' :
                        Math.round(age / 3600) + 'h ago';
                    let title = dot.getAttribute('title').split(' —')[0];
                    title += ' — ' + info.status + ' (' + ageText + ')';
                    if (info.error_count > 0) title += ' | ' + info.error_count + ' errors';
                    if (info.last_error_msg) title += ': ' + info.last_error_msg;
                    dot.setAttribute('title', title);
                });
            })
            .catch(() => {});
    },

    start() {
        this.poll();
        setInterval(() => this.poll(), 30000);  // every 30s
    }
};

document.addEventListener('DOMContentLoaded', () => DataHealth.start());
```

**Step 4: Test visually**

Open dashboard in browser. The navbar should show 7 small dots next to the WebSocket status indicator. After collectors have run, dots should turn green. Hover to see tooltip with source name, status, and age.

**Step 5: Commit**

```bash
git add templates/base.html static/css/style.css static/js/ws.js
git commit -m "feat: add data freshness badges to navbar"
```

---

### Task 6: Update API docs

**Files:**
- Modify: `docs/API.md`

**Step 1: Add health endpoint documentation**

Add a new section after the Threats section:

```markdown
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
```

**Step 2: Commit**

```bash
git add docs/API.md
git commit -m "docs: add health endpoint to API reference"
```

---

## Checkpoint: Send to Codex for Review

After Task 6, run Codex review against the feature branch to validate the implementation before merging.
