"""Cyber intelligence collector: IODA outage detection, cyber news RSS, CISA KEV."""

import calendar
import hashlib
import json
import logging
import math
import os
import time
from datetime import datetime, timedelta

import feedparser
import httpx

from collectors.base import BaseCollector
from config import (
    CYBER_POLL_INTERVAL, CISA_KEV_URL,
    IODA_API_BASE, IODA_ALERT_LOOKBACK, IODA_EVENT_LOOKBACK,
    IODA_WATCHED_COUNTRIES, IODA_SIGNAL_DATASOURCES,
    IODA_SIGNAL_LOOKBACK, IODA_SIGNAL_MAX_POINTS,
    CYBER_NEWS_FEEDS, HTTP_TIMEOUT, HTTP_USER_AGENT,
)
from ws_manager import manager

logger = logging.getLogger(__name__)

# New payload cache (dict)
cyber_cache: dict = {
    "outages": [],
    "cyber_news": [],
    "cves": [],
    "stats": {"active_outages": 0, "countries_affected": 0, "new_cves": 0},
    "correlations": [],
    "watched_signals": {},
    "last_updated": None,
}

# Legacy compat: scoring.py expects a list of event dicts via main.py
# This stays empty since we no longer produce IOC-style events.
cyber_events_legacy: list[dict] = []

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


# Country code → geo mapping (self-contained, not shared with config.py)
COUNTRY_GEO = {
    "TW": {"name": "Taiwan",        "lat": 24.0,  "lon": 121.0, "region": "Taiwan Strait"},
    "CN": {"name": "China",         "lat": 35.0,  "lon": 105.0, "region": "East Asia"},
    "UA": {"name": "Ukraine",       "lat": 49.0,  "lon": 32.0,  "region": "East Ukraine"},
    "RU": {"name": "Russia",        "lat": 55.75, "lon": 37.6,  "region": "Russia"},
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


def _normalize_score(raw_score: float) -> int:
    """Map IODA's raw score (varies ~1k to ~2M) to 1-10 severity using log scale."""
    if raw_score <= 0:
        return 1
    log_val = math.log10(max(raw_score, 1))
    # Empirical: scores range from ~10^3 (minor) to ~10^6 (massive)
    # Map log10(1000)=3 → 1, log10(1000000)=6 → 10
    severity = int((log_val - 3) * 3) + 1
    return max(1, min(severity, 10))


class CyberCollector(BaseCollector):
    def __init__(self):
        super().__init__("cyber", CYBER_POLL_INTERVAL)
        self._seen_urls: set[str] = set()

    async def _fetch_ioda_events(self, client: httpx.AsyncClient) -> list[dict]:
        """Fetch confirmed outage events from IODA for monitored countries."""
        now = int(time.time())
        params = {
            "entityType": "country",
            "from": now - IODA_EVENT_LOOKBACK,
            "until": now,
        }
        try:
            resp = await client.get(f"{IODA_API_BASE}/outages/events", params=params)
            resp.raise_for_status()
        except Exception as e:
            logger.error(f"[cyber] IODA events: {e}")
            return []

        data = resp.json().get("data", [])
        # Deduplicate: keep best (highest score) per country+datasource
        best: dict[str, dict] = {}
        for event in data:
            loc = event.get("location", "")
            code = loc.split("/")[-1] if "/" in loc else loc
            if code not in COUNTRY_GEO:
                continue
            geo = COUNTRY_GEO[code]
            ds = event.get("datasource", "unknown")
            key = f"{code}:{ds}"
            score = event.get("score", 0) or 0
            if key in best and best[key]["raw_score"] >= score:
                continue
            best[key] = {
                "country_code": code,
                "country_name": geo["name"],
                "region": geo["region"],
                "lat": geo["lat"],
                "lon": geo["lon"],
                "severity": _normalize_score(score),
                "datasource": ds,
                "start": event.get("start", 0),
                "duration": event.get("duration", 0),
                "raw_score": score,
            }
        return sorted(best.values(), key=lambda e: e["severity"], reverse=True)

    async def _fetch_ioda_alerts(self, client: httpx.AsyncClient) -> list[dict]:
        """Fetch real-time outage alerts (critical only) for monitored countries."""
        now = int(time.time())
        params = {
            "entityType": "country",
            "from": now - IODA_ALERT_LOOKBACK,
            "until": now,
        }
        try:
            resp = await client.get(f"{IODA_API_BASE}/outages/alerts", params=params)
            resp.raise_for_status()
        except Exception as e:
            logger.error(f"[cyber] IODA alerts: {e}")
            return []

        data = resp.json().get("data", [])
        alerts = []
        seen = set()
        for alert in data:
            if alert.get("level") != "critical":
                continue
            entity = alert.get("entity", {})
            code = entity.get("code", "")
            if code not in COUNTRY_GEO:
                continue
            ds = alert.get("datasource", "unknown")
            key = f"{code}:{ds}"
            if key in seen:
                continue
            seen.add(key)
            geo = COUNTRY_GEO[code]
            history = alert.get("historyValue", 0) or 1
            value = alert.get("value", 0) or 0
            drop_pct = max(0, (1 - value / history) * 100) if history > 0 else 0
            alerts.append({
                "country_code": code,
                "country_name": geo["name"],
                "region": geo["region"],
                "lat": geo["lat"],
                "lon": geo["lon"],
                "datasource": ds,
                "drop_pct": round(drop_pct, 1),
                "time": alert.get("time", 0),
            })
        return alerts

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

    async def _fetch_cyber_news(self, client: httpx.AsyncClient) -> list[dict]:
        """Fetch cyber-specific RSS feeds (self-contained, not via NewsCollector)."""
        self._seen_urls.clear()  # Reset each poll — show all recent articles
        articles = []
        for source, url in CYBER_NEWS_FEEDS.items():
            try:
                resp = await client.get(url)
                if resp.status_code != 200:
                    logger.warning(f"[cyber] RSS {source} returned {resp.status_code}")
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

                    link = entry.get("link", "")
                    url_hash = hashlib.sha256(link.encode()).hexdigest()[:16]
                    if url_hash in self._seen_urls:
                        continue
                    self._seen_urls.add(url_hash)

                    articles.append({
                        "title": entry.get("title", ""),
                        "url": link,
                        "source": source,
                        "published": entry.get("published", ""),
                        "published_ts": pub_ts,
                        "summary": (entry.get("summary", "") or "")[:300],
                    })
            except Exception as e:
                logger.error(f"[cyber] RSS {source}: {e}")
        # Sort by publication time, newest first
        articles.sort(key=lambda a: a.get("published_ts") or 0, reverse=True)
        return articles[:50]

    async def _fetch_cisa_kev(self, client: httpx.AsyncClient) -> tuple[list[dict], int]:
        """Fetch CISA Known Exploited Vulnerabilities catalog."""
        try:
            resp = await client.get(CISA_KEV_URL)
            if resp.status_code != 200:
                logger.warning(f"[cyber] CISA KEV returned {resp.status_code}")
                return [], 0
            data = resp.json()
            vulns = data.get("vulnerabilities", [])
            today = datetime.utcnow().strftime("%Y-%m-%d")
            this_month = today[:7]
            recent = [v for v in vulns if v.get("dateAdded", "") >= this_month][:20]
            new_today = len([v for v in vulns if v.get("dateAdded", "") == today])

            cves = []
            for v in recent:
                cves.append({
                    "cve_id": v.get("cveID", "N/A"),
                    "title": v.get("vulnerabilityName", ""),
                    "severity": "Critical" if "critical" in v.get("vulnerabilityName", "").lower() else "High",
                    "description": v.get("shortDescription", "")[:200],
                    "date_added": v.get("dateAdded", ""),
                })
            return cves, new_today
        except Exception as e:
            logger.error(f"[cyber] CISA KEV: {e}")
            return [], 0

    async def _correlate(self, outages: list[dict], articles: list[dict]) -> list[dict]:
        """Check for IODA outage + cyber news geographic overlap. Send to LLM if found."""
        correlations = []
        for outage in outages:
            if outage["severity"] < 3:
                continue
            country_lower = outage["country_name"].lower()
            matches = [
                a for a in articles
                if country_lower in a["title"].lower()
                or country_lower in a.get("summary", "").lower()
            ]
            if not matches:
                continue

            correlation = {
                "country": outage["country_name"],
                "region": outage["region"],
                "outage_severity": outage["severity"],
                "datasource": outage["datasource"],
                "matched_articles": len(matches),
                "article_titles": [a["title"] for a in matches[:3]],
            }
            correlations.append(correlation)

            # Send to threat engine for LLM assessment
            title = (
                f"Internet disruption in {outage['country_name']} "
                f"({outage['datasource']}, severity {outage['severity']}/10) "
                f"with {len(matches)} related cyber news"
            )
            body = (
                f"IODA detected a severity {outage['severity']}/10 internet disruption "
                f"in {outage['country_name']} (datasource: {outage['datasource']}, "
                f"duration: {outage['duration']}s). "
                f"Related articles: {'; '.join(a['title'] for a in matches[:3])}"
            )
            try:
                import threat_engine
                result = await threat_engine.assess(
                    "cyber", title, body,
                    extra={
                        "geo_region": outage["region"],
                        "country": outage["country_name"],
                        "outage_severity": outage["severity"],
                    },
                )
                if result:
                    correlation["llm_assessment"] = result.get("summary", "")
                    correlation["confidence"] = result.get("confidence", "unknown")
            except Exception as e:
                logger.error(f"[cyber] Correlation assess error: {e}")

        return correlations

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

                    entries = []
                    for i, val in enumerate(valid):
                        day = datetime.utcfromtimestamp(now - (len(valid) - i) * 86400).strftime("%Y-%m-%d")
                        entries.append({"date": day, "avg": round(val, 2)})

                    history[code][ds] = entries
                    logger.info(f"[cyber] Backfilled {code}/{ds}: {len(entries)} days")
                except Exception as e:
                    logger.error(f"[cyber] Backfill {code}/{ds}: {e}")

        _save_signal_history(history)

    async def collect(self):
        async with httpx.AsyncClient(
            timeout=HTTP_TIMEOUT,
            headers={"User-Agent": HTTP_USER_AGENT},
        ) as client:
            # One-time backfill of 7-day history on first run
            await self._backfill_signal_history(client)

            # Fetch all sources
            outage_events = await self._fetch_ioda_events(client)
            outage_alerts = await self._fetch_ioda_alerts(client)
            watched_signals = await self._fetch_watched_signals(client)
            cyber_news = await self._fetch_cyber_news(client)
            cves, new_cve_count = await self._fetch_cisa_kev(client)

        # Merge alerts into events (alerts are real-time, events are confirmed)
        # Use events as primary, add alert-only countries
        event_keys = {f"{e['country_code']}:{e['datasource']}" for e in outage_events}
        for alert in outage_alerts:
            key = f"{alert['country_code']}:{alert['datasource']}"
            if key not in event_keys:
                outage_events.append({
                    "country_code": alert["country_code"],
                    "country_name": alert["country_name"],
                    "region": alert["region"],
                    "lat": alert["lat"],
                    "lon": alert["lon"],
                    "severity": max(3, int(alert["drop_pct"] / 10)),
                    "datasource": alert["datasource"],
                    "start": alert.get("time", 0),
                    "duration": 0,
                    "raw_score": 0,
                    "alert_drop_pct": alert["drop_pct"],
                })

        # Run correlation
        correlations = await self._correlate(outage_events, cyber_news)

        # Count feeds that returned data (for display)
        feeds_ok = 0
        if outage_events or outage_alerts:
            feeds_ok += 1
        if cyber_news:
            feeds_ok += 1
        if cves:
            feeds_ok += 1

        # Preserve last-known-good signals on transient failure
        if not any(s.get("datasources") for s in watched_signals.values()):
            watched_signals = cyber_cache.get("watched_signals", {})

        now_iso = datetime.utcnow().isoformat() + "Z"

        # Update cache
        cyber_cache.update({
            "outages": outage_events,
            "cyber_news": cyber_news,
            "cves": cves,
            "stats": {
                "active_outages": len(outage_events),
                "countries_affected": len(set(o["country_code"] for o in outage_events)),
                "new_cves": new_cve_count,
                "feeds_ok": feeds_ok,
            },
            "correlations": correlations,
            "watched_signals": watched_signals,
            "last_updated": now_iso,
        })

        # Broadcast via WebSocket
        await manager.broadcast("cyber", cyber_cache)

        sig_count = sum(len(s.get("datasources", {})) for s in watched_signals.values())
        logger.info(
            f"[cyber] {len(outage_events)} outages, {len(cyber_news)} articles, "
            f"{len(cves)} CVEs, {len(correlations)} correlations, {feeds_ok}/3 feeds ok, "
            f"{len(watched_signals)} watched ({sig_count} signals)"
        )

        # Only raise if every HTTP call failed (not just empty results)
        if feeds_ok == 0 and not watched_signals:
            raise RuntimeError("All cyber feeds returned zero data")

        return cyber_cache
