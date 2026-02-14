"""Threat scoring algorithm for regions."""

import logging

logger = logging.getLogger(__name__)

KEYWORD_WEIGHTS = {
    "war": 10, "invasion": 10, "nuclear": 10,
    "missile": 9, "airstrike": 9, "bombing": 9,
    "attack": 8, "troops": 8, "military": 7,
    "conflict": 7, "casualties": 7, "killed": 7,
    "strike": 6, "weapon": 6, "drone": 6,
    "sanctions": 5, "threat": 5, "escalation": 5,
    "tension": 4, "deployment": 4, "exercise": 4,
    "protest": 3, "crisis": 3, "warning": 3,
    "negotiation": 2, "diplomacy": 2, "ceasefire": 2,
}


def score_text(text: str) -> float:
    """Score a text string based on threat keywords."""
    text_lower = text.lower()
    score = 0.0
    for keyword, weight in KEYWORD_WEIGHTS.items():
        if keyword in text_lower:
            score += weight
    return score


def compute_region_scores(articles: list, military_assets: list, cyber_events: list) -> dict:
    """Compute threat scores (0-100) per region."""
    region_scores = {}

    # News contribution
    for article in articles:
        region = article.get("geo_region")
        if not region:
            continue
        text_score = score_text(article.get("title", "") + " " + article.get("summary", ""))
        region_scores.setdefault(region, {"news": 0, "news_count": 0, "military": 0, "cyber": 0})
        region_scores[region]["news"] += text_score
        region_scores[region]["news_count"] += 1

    # Military contribution
    for asset in military_assets:
        region = asset.get("region")
        if not region:
            continue
        region_scores.setdefault(region, {"news": 0, "news_count": 0, "military": 0, "cyber": 0})
        region_scores[region]["military"] += 5

    # Cyber contribution
    for event in cyber_events:
        severity_map = {"critical": 10, "high": 7, "medium": 4, "low": 2}
        sev = event.get("severity", "low").lower()
        region_scores.setdefault("Global", {"news": 0, "news_count": 0, "military": 0, "cyber": 0})
        region_scores["Global"]["cyber"] += severity_map.get(sev, 1)

    # Normalize to 0-100
    result = {}
    for region, components in region_scores.items():
        raw = (
            min(components["news"], 50) +
            min(components["news_count"] * 2, 20) +
            min(components["military"], 20) +
            min(components["cyber"], 10)
        )
        result[region] = min(int(raw), 100)

    return result
