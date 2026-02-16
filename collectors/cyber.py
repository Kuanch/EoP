"""Cyber threat intelligence collector: CISA KEV, Abuse.ch, AlienVault OTX."""

import logging
from datetime import datetime

import httpx

from collectors.base import BaseCollector
from config import (
    CYBER_POLL_INTERVAL, CISA_KEV_URL, FEODO_URL,
    OTX_PULSE_URL, OTX_API_KEY, HTTP_TIMEOUT, HTTP_USER_AGENT,
)
from ws_manager import manager

logger = logging.getLogger(__name__)

cyber_cache: list[dict] = []
stats_cache: dict = {"total_iocs": 0, "active_campaigns": 0, "new_cves": 0, "threat_level": "Low"}


class CyberCollector(BaseCollector):
    def __init__(self):
        super().__init__("cyber", CYBER_POLL_INTERVAL)
        self.db_session_factory = None

    def set_db(self, session_factory):
        self.db_session_factory = session_factory

    async def collect(self):
        events = []
        total_iocs = 0
        new_cves = 0
        active_campaigns = 0

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
                except Exception as e:
                    logger.error(f"[cyber] OTX: {e}")

        # Determine threat level
        if total_iocs > 100 or new_cves > 5:
            threat_level = "Critical"
        elif total_iocs > 50 or new_cves > 2:
            threat_level = "High"
        elif total_iocs > 20:
            threat_level = "Medium"
        else:
            threat_level = "Low"

        # Sort by severity
        severity_order = {"Critical": 0, "High": 1, "Medium": 2, "Low": 3}
        events.sort(key=lambda e: severity_order.get(e.get("severity", "Low"), 3))

        cyber_cache.clear()
        cyber_cache.extend(events)
        stats_cache.update({
            "total_iocs": total_iocs,
            "active_campaigns": active_campaigns,
            "new_cves": new_cves,
            "threat_level": threat_level,
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
            if e.get("severity") in ("Critical", "High"):
                try:
                    await threat_engine.assess("cyber", e["title"], e.get("description", ""),
                                               extra={"severity": e["severity"]})
                except Exception as ex:
                    logger.error(f"[cyber] Threat assess error: {ex}")
        return events
