"""Rule-based cyber escalation classifier.

Converts generic cyber events into more useful geopolitical signal metadata.
"""

from __future__ import annotations

import re

from config import GEO_KEYWORDS

ESCALATION_KEYWORDS = {
    "government": 4,
    "ministry": 4,
    "military": 5,
    "defense": 5,
    "telecom": 4,
    "telco": 4,
    "satellite": 5,
    "airport": 4,
    "aviation": 4,
    "seaport": 4,
    "harbor": 4,
    "shipping": 3,
    "rail": 4,
    "railway": 4,
    "energy": 4,
    "oil": 3,
    "gas": 3,
    "power": 4,
    "grid": 5,
    "bank": 4,
    "finance": 4,
    "ddos": 4,
    "disruption": 4,
    "outage": 5,
    "wiper": 6,
    "destructive": 6,
    "sabotage": 6,
    "jam": 5,
    "jamming": 5,
    "gps": 5,
    "gnss": 5,
    "apt": 4,
    "state-sponsored": 5,
    "critical infrastructure": 6,
}

SECTOR_KEYWORDS = {
    "government": ("government", "ministry", "embassy", "parliament"),
    "military": ("military", "defense", "army", "navy", "air force"),
    "telecom": ("telecom", "telco", "mobile network", "isp", "internet provider"),
    "energy": ("energy", "oil", "gas", "pipeline", "power", "grid", "electricity"),
    "transport": ("airport", "aviation", "rail", "railway", "seaport", "harbor", "shipping", "marine terminal"),
    "satellite": ("satellite", "gps", "gnss", "space"),
    "finance": ("bank", "finance", "payment", "exchange", "swift"),
    "critical_infra": ("critical infrastructure", "water utility", "datacenter"),
}

SOURCE_BASELINES = {
    "CISA KEV": 2,
    "Abuse.ch Feodo": 1,
    "AlienVault OTX": 2,
    "URLhaus": 1,
    "C2IntelFeeds": 1,
}

SOURCE_CONFIDENCE = {
    "CISA KEV": "high",
    "Abuse.ch Feodo": "medium",
    "AlienVault OTX": "medium",
    "URLhaus": "medium",
    "C2IntelFeeds": "low",
}


def _has_keyword(text: str, keyword: str) -> bool:
    pattern = r"(?<![a-z0-9])" + re.escape(keyword.lower()) + r"(?![a-z0-9])"
    return re.search(pattern, text) is not None


def _infer_region(text: str) -> str:
    text_lower = text.lower()
    for keyword, geo in GEO_KEYWORDS.items():
        if not geo or not _has_keyword(text_lower, keyword):
            continue
        return geo[2]
    return "Global"


def _infer_sector(text: str) -> str:
    text_lower = text.lower()
    for sector, keywords in SECTOR_KEYWORDS.items():
        if any(_has_keyword(text_lower, keyword) for keyword in keywords):
            return sector
    return "unknown"


def classify_event(event: dict) -> dict:
    """Annotate a cyber event with escalation metadata."""
    title = event.get("title", "")
    description = event.get("description", "")
    source = event.get("source", "")
    event_type = event.get("type", "")
    text = f"{title} {description}".lower()

    score = SOURCE_BASELINES.get(source, 1)
    for keyword, weight in ESCALATION_KEYWORDS.items():
        if _has_keyword(text, keyword):
            score += weight

    if event_type in {"malware_url", "c2_community"}:
        score = min(score, 4)
    elif event_type == "cve":
        score += 1

    sector = _infer_sector(text)
    region = _infer_region(text)
    confidence = SOURCE_CONFIDENCE.get(source, "low")

    if region != "Global":
        score += 2
    if sector in {"government", "military", "satellite", "critical_infra"}:
        score += 2

    if score >= 9:
        escalation_level = "strategic"
    elif score >= 5:
        escalation_level = "elevated"
    else:
        escalation_level = "background"

    war_signal = escalation_level != "background" and region != "Global"

    return {
        "escalation_score": min(score, 10),
        "escalation_level": escalation_level,
        "geo_region": region,
        "target_sector": sector,
        "attribution_confidence": confidence,
        "war_signal": war_signal,
    }
