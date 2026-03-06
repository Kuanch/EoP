"""Cyber threat intelligence collector: CISA KEV, Abuse.ch, OTX, URLhaus, C2Intel."""

import csv
import io
import logging
from datetime import datetime

import httpx

from collectors.base import BaseCollector
from cyber_escalation import classify_event
from config import (
    CYBER_POLL_INTERVAL, CISA_KEV_URL, FEODO_URL,
    OTX_PULSE_URL, OTX_API_KEY, URLHAUS_CSV_URL, C2INTEL_CSV_URL,
    HTTP_TIMEOUT, HTTP_USER_AGENT,
)
from ws_manager import manager

logger = logging.getLogger(__name__)

cyber_cache: list[dict] = []
stats_cache: dict = {
    "total_iocs": 0,
    "active_campaigns": 0,
    "new_cves": 0,
    "threat_level": "Low",
    "source_counts": {},
    "escalation_summary": {},
}


class CyberCollector(BaseCollector):
    def __init__(self):
        super().__init__("cyber", CYBER_POLL_INTERVAL)
        self.db_session_factory = None

    def set_db(self, session_factory):
        self.db_session_factory = session_factory

    async def _fetch_urlhaus(self, client: httpx.AsyncClient) -> tuple[list[dict], int]:
        resp = await client.get(URLHAUS_CSV_URL)
        resp.raise_for_status()

        rows: list[str] = []
        for line in resp.text.splitlines():
            if not line.strip():
                continue
            if line.startswith("# id,"):
                rows.append(line.lstrip("# ").strip())
                continue
            if line.startswith("#"):
                continue
            rows.append(line)

        if not rows:
            return [], 0

        reader = csv.DictReader(io.StringIO("\n".join(rows)))
        events = []
        online_count = 0

        for row in reader:
            if row.get("url_status") != "online":
                continue
            online_count += 1
            if len(events) >= 20:
                continue

            tags = row.get("tags", "").strip()
            threat = row.get("threat", "").replace("_", " ").strip() or "malware"
            description = threat.title()
            if tags:
                description = f"{description} | Tags: {tags[:120]}"

            events.append({
                "type": "malware_url",
                "title": row.get("url", "Unknown URL"),
                "severity": "High",
                "source": "URLhaus",
                "description": description,
                "ioc_count": 1,
                "timestamp": row.get("dateadded", ""),
            })

        return events, online_count

    async def _fetch_c2intel(self, client: httpx.AsyncClient) -> tuple[list[dict], int]:
        resp = await client.get(C2INTEL_CSV_URL)
        resp.raise_for_status()

        rows = []
        for line in resp.text.splitlines():
            if not line.strip():
                continue
            if line.startswith("#ip,"):
                rows.append(line.lstrip("# ").strip())
                continue
            rows.append(line)

        reader = csv.DictReader(io.StringIO("\n".join(rows)))
        events = []
        row_count = 0

        for row in reader:
            ip = (row.get("ip") or "").strip()
            ioc = (row.get("ioc") or "").strip()
            if not ip:
                continue
            row_count += 1
            if len(events) >= 20:
                continue
            events.append({
                "type": "c2_community",
                "title": f"C2 Indicator: {ip}",
                "severity": "Medium",
                "source": "C2IntelFeeds",
                "description": ioc or "Community-reported C2 indicator",
                "ioc_count": 1,
                "timestamp": datetime.utcnow().isoformat(),
            })

        return events, row_count

    async def collect(self):
        events = []
        total_iocs = 0
        new_cves = 0
        active_campaigns = 0
        source_counts = {
            "cisa_kev": 0,
            "feodo": 0,
            "otx": 0,
            "urlhaus": 0,
            "c2intel": 0,
        }
        escalation_summary = {"background": 0, "elevated": 0, "strategic": 0, "war_signals": 0}

        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT, headers={"User-Agent": HTTP_USER_AGENT}) as client:
            # CISA KEV
            try:
                resp = await client.get(CISA_KEV_URL)
                if resp.status_code == 200:
                    data = resp.json()
                    vulns = data.get("vulnerabilities", [])
                    today = datetime.utcnow().strftime("%Y-%m-%d")
                    recent = [v for v in vulns if v.get("dateAdded", "") >= today[:7]][:20]
                    new_cves = len([v for v in vulns if v.get("dateAdded", "") == today])

                    for v in recent:
                        events.append({
                            "type": "cve",
                            "title": f"{v.get('cveID', 'N/A')}: {v.get('vulnerabilityName', '')}",
                            "severity": "Critical" if "critical" in v.get("vulnerabilityName", "").lower() else "High",
                            "source": "CISA KEV",
                            "description": v.get("shortDescription", ""),
                            "ioc_count": 1,
                            "timestamp": v.get("dateAdded", ""),
                        })
                    total_iocs += len(recent)
                    source_counts["cisa_kev"] = len(recent)
            except Exception as e:
                logger.error(f"[cyber] CISA KEV: {e}")

            # Abuse.ch Feodo
            try:
                resp = await client.get(FEODO_URL)
                if resp.status_code == 200:
                    data = resp.json()
                    entries = data if isinstance(data, list) else data.get("data", data.get("entries", []))
                    if isinstance(entries, list):
                        active = entries[:20]
                        active_campaigns = len(set(e.get("malware", "") for e in active if isinstance(e, dict)))
                        for entry in active:
                            if not isinstance(entry, dict):
                                continue
                            events.append({
                                "type": "c2",
                                "title": f"C2 Server: {entry.get('ip_address', entry.get('dst_ip', 'N/A'))}",
                                "severity": "High",
                                "source": "Abuse.ch Feodo",
                                "description": f"Malware: {entry.get('malware', 'Unknown')} Port: {entry.get('dst_port', 'N/A')}",
                                "ioc_count": 1,
                                "timestamp": entry.get("first_seen", entry.get("date_added", "")),
                            })
                        total_iocs += len(active)
                        source_counts["feodo"] = len(active)
            except Exception as e:
                logger.error(f"[cyber] Abuse.ch: {e}")

            # AlienVault OTX (if API key provided)
            if OTX_API_KEY:
                try:
                    resp = await client.get(
                        OTX_PULSE_URL,
                        headers={"X-OTX-API-KEY": OTX_API_KEY},
                        params={"limit": 10},
                    )
                    if resp.status_code == 200:
                        data = resp.json()
                        for pulse in data.get("results", [])[:10]:
                            ioc_count = len(pulse.get("indicators", []))
                            events.append({
                                "type": "pulse",
                                "title": pulse.get("name", "Unknown Pulse"),
                                "severity": "Medium",
                                "source": "AlienVault OTX",
                                "description": pulse.get("description", "")[:200],
                                "ioc_count": ioc_count,
                                "timestamp": pulse.get("created", ""),
                            })
                            total_iocs += ioc_count
                            source_counts["otx"] += ioc_count
                except Exception as e:
                    logger.error(f"[cyber] OTX: {e}")

            # URLhaus malware URLs
            try:
                urlhaus_events, urlhaus_count = await self._fetch_urlhaus(client)
                events.extend(urlhaus_events)
                total_iocs += urlhaus_count
                source_counts["urlhaus"] = urlhaus_count
            except Exception as e:
                logger.error(f"[cyber] URLhaus: {e}")

            # Community C2 feed
            try:
                c2intel_events, c2intel_count = await self._fetch_c2intel(client)
                events.extend(c2intel_events)
                total_iocs += c2intel_count
                source_counts["c2intel"] = c2intel_count
            except Exception as e:
                logger.error(f"[cyber] C2IntelFeeds: {e}")

        effective_iocs = sum(min(count, 40) for count in source_counts.values())

        # Determine threat level without letting very large community feeds pin the score forever.
        if effective_iocs > 120 or new_cves > 5:
            threat_level = "Critical"
        elif effective_iocs > 60 or new_cves > 2:
            threat_level = "High"
        elif effective_iocs > 20:
            threat_level = "Medium"
        else:
            threat_level = "Low"

        # Add geopolitical escalation metadata before sorting and downstream scoring.
        for event in events:
            event.update(classify_event(event))
            level = event.get("escalation_level", "background")
            escalation_summary[level] = escalation_summary.get(level, 0) + 1
            if event.get("war_signal"):
                escalation_summary["war_signals"] += 1

        # Sort by severity first, then escalation level.
        severity_order = {"Critical": 0, "High": 1, "Medium": 2, "Low": 3}
        escalation_order = {"strategic": 0, "elevated": 1, "background": 2}
        events.sort(key=lambda e: (
            severity_order.get(e.get("severity", "Low"), 3),
            escalation_order.get(e.get("escalation_level", "background"), 2),
        ))

        cyber_cache.clear()
        cyber_cache.extend(events)
        stats_cache.update({
            "total_iocs": total_iocs,
            "active_campaigns": active_campaigns,
            "new_cves": new_cves,
            "threat_level": threat_level,
            "source_counts": source_counts,
            "escalation_summary": escalation_summary,
        })

        # Persist to DB
        if self.db_session_factory:
            try:
                from database import ThreatEvent
                db = self.db_session_factory()
                try:
                    for e in events[:50]:
                        db.add(ThreatEvent(
                            event_type=e["type"],
                            title=e["title"],
                            severity=e["severity"],
                            source=e["source"],
                            description=e.get("description", ""),
                            ioc_count=e.get("ioc_count", 0),
                        ))
                    db.commit()
                finally:
                    db.close()
            except Exception as e:
                logger.error(f"[cyber] DB persist error: {e}")

        await manager.broadcast("cyber", {"events": events, "stats": stats_cache})
        logger.info(f"[cyber] {len(events)} events, {total_iocs} IOCs")

        # Threat engine assessment
        import threat_engine
        for e in events:
            should_assess = (
                e.get("escalation_level") in ("elevated", "strategic") or
                (e.get("source") in {"CISA KEV", "AlienVault OTX"} and e.get("severity") in ("Critical", "High"))
            )
            if should_assess:
                try:
                    await threat_engine.assess("cyber", e["title"], e.get("description", ""),
                                               extra={
                                                   "severity": e["severity"],
                                                   "geo_region": e.get("geo_region"),
                                                   "escalation_level": e.get("escalation_level"),
                                                   "escalation_score": e.get("escalation_score"),
                                                   "target_sector": e.get("target_sector"),
                                                   "attribution_confidence": e.get("attribution_confidence"),
                                                   "war_signal": e.get("war_signal"),
                                               })
                except Exception as ex:
                    logger.error(f"[cyber] Threat assess error: {ex}")
        return events
