"""Cyber intelligence collector: IODA outage detection, cyber news RSS, CISA KEV."""

import calendar
import hashlib
import logging
import math
import time
from datetime import datetime

import feedparser
import httpx

from collectors.base import BaseCollector
from config import (
    CYBER_POLL_INTERVAL, CISA_KEV_URL,
    IODA_API_BASE, IODA_ALERT_LOOKBACK, IODA_EVENT_LOOKBACK,
    IODA_WATCHED_COUNTRIES, IODA_SIGNAL_DATASOURCES,
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
        """Fetch real-time signal levels for watched countries (TW, UA).

        Returns {country_code: {datasource: {values, pct_change, status}}}
        so the frontend can show continuous health even without declared outages.
        """
        now = int(time.time())
        lookback = 6 * 3600  # 6 hours of data
        signals: dict[str, dict] = {}

        for code in IODA_WATCHED_COUNTRIES:
            if code not in COUNTRY_GEO:
                continue
            geo = COUNTRY_GEO[code]
            signals[code] = {"name": geo["name"], "lat": geo["lat"], "lon": geo["lon"],
                             "region": geo["region"], "datasources": {}}

            for ds in IODA_SIGNAL_DATASOURCES:
                try:
                    resp = await client.get(
                        f"{IODA_API_BASE}/signals/raw/country/{code}",
                        params={"datasource": ds, "from": now - lookback, "until": now, "maxPoints": 12},
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
                            "pct_change": 0,
                            "status": "unknown",
                            "values": values,
                        }
                        continue

                    current = valid[-1]
                    baseline = sum(valid[:-1]) / len(valid[:-1])

                    if baseline == 0:
                        pct_change = 0
                    else:
                        pct_change = round((current - baseline) / baseline * 100, 1)

                    # Classify health
                    if pct_change < -30:
                        status = "critical"
                    elif pct_change < -15:
                        status = "degraded"
                    elif pct_change < -5:
                        status = "warning"
                    else:
                        status = "normal"

                    signals[code]["datasources"][ds] = {
                        "current": round(current, 1),
                        "baseline": round(baseline, 1),
                        "pct_change": pct_change,
                        "status": status,
                        "values": [round(v, 1) if v is not None else None for v in values],
                    }
                except Exception as e:
                    logger.error(f"[cyber] Signal {code}/{ds}: {e}")

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

    async def collect(self):
        async with httpx.AsyncClient(
            timeout=HTTP_TIMEOUT,
            headers={"User-Agent": HTTP_USER_AGENT},
        ) as client:
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
