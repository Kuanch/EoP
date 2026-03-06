"""Hybrid threat detection: rule-based scoring + LLM classification."""

import json
import logging
import os
import time
from collections import deque
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)

CONFIG_PATH = Path(__file__).parent / "threat_rules.json"
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

# In-memory threat feed
threat_feed: deque = deque(maxlen=500)

# Stats
stats = {"threats_today": 0, "notifications_sent": 0, "llm_calls": 0, "day": ""}

# Cooldown tracker
_cooldowns: dict[str, float] = {}


def load_config() -> dict:
    """Load threat rules config from JSON file."""
    try:
        with open(CONFIG_PATH) as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"[threat] Failed to load config: {e}")
        return {
            "keyword_rules": {},
            "llm_threshold": 5,
            "notify_threshold": 7,
            "llm_enabled": False,
            "llm_prompt": "",
            "cooldown_minutes": 15,
            "sources": {"news": True, "cyber": True, "pizzint": True},
        }


def save_config(config: dict):
    """Save threat rules config to JSON file."""
    try:
        with open(CONFIG_PATH, "w") as f:
            json.dump(config, f, indent=2)
        logger.info(f"[threat] Config saved successfully")
    except Exception as e:
        logger.error(f"[threat] Failed to save config: {e}")
        raise


def _reset_daily_stats():
    """Reset stats if new day."""
    from datetime import datetime
    today = datetime.utcnow().strftime("%Y-%m-%d")
    if stats["day"] != today:
        stats["threats_today"] = 0
        stats["notifications_sent"] = 0
        stats["llm_calls"] = 0
        stats["day"] = today


def score_by_rules(text: str, rules: dict) -> float:
    """Score text against keyword rules."""
    text_lower = text.lower()
    score = 0.0
    for keyword, weight in rules.items():
        if keyword in text_lower:
            score += weight
    return score


async def _translate_for_notify(text: str) -> str | None:
    """Translate notification text to Traditional Chinese via Claude Haiku."""
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": ANTHROPIC_API_KEY,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": "claude-haiku-4-5-20251001",
                    "max_tokens": 300,
                    "messages": [
                        {"role": "user", "content": f"Translate the following threat alert to Traditional Chinese (繁體中文). Keep it concise. Only return the translation, nothing else.\n\n{text[:500]}"}
                    ],
                },
            )
            if resp.status_code == 200:
                data = resp.json()
                return data["content"][0]["text"].strip()
    except Exception as e:
        logger.warning(f"[threat] Translation failed: {e}")
    return None


async def call_llm(text: str, prompt: str) -> dict | None:
    """Call Claude Haiku for threat classification."""
    if not ANTHROPIC_API_KEY:
        logger.warning("[threat] No ANTHROPIC_API_KEY set, skipping LLM")
        return None

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": ANTHROPIC_API_KEY,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": "claude-haiku-4-5-20251001",
                    "max_tokens": 150,
                    "messages": [
                        {"role": "user", "content": f"{prompt}\n\nItem: {text[:1000]}"}
                    ],
                },
            )
            if resp.status_code != 200:
                logger.error(f"[threat] LLM API {resp.status_code}: {resp.text[:200]}")
                return None

            data = resp.json()
            content = data["content"][0]["text"].strip()
            # Strip markdown fences if present
            if content.startswith("```"):
                content = content.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
            result = json.loads(content)
            stats["llm_calls"] += 1
            return result
    except json.JSONDecodeError:
        logger.warning(f"[threat] LLM returned non-JSON: {content[:200]}")
        return None
    except Exception as e:
        logger.error(f"[threat] LLM call failed: {e}")
        return None


async def assess(source: str, title: str, text: str, extra: dict | None = None) -> dict:
    """Assess a single item through the hybrid pipeline.

    Returns assessment dict with rule_score, llm_score, rationale, notified.
    """
    _reset_daily_stats()
    config = load_config()

    # Check if source is enabled
    if not config.get("sources", {}).get(source, True):
        return {}

    # Pass 1: Rule-based scoring
    rule_score = score_by_rules(title + " " + text, config.get("keyword_rules", {}))

    assessment = {
        "timestamp": time.time(),
        "source": source,
        "title": title[:200],
        "text": text[:300],
        "rule_score": round(rule_score, 1),
        "llm_score": None,
        "llm_threat_type": None,
        "llm_rationale": None,
        "final_score": round(rule_score, 1),
        "notified": False,
    }
    if extra:
        assessment.update(extra)

    # Pass 2: LLM classification (if threshold met)
    llm_threshold = config.get("llm_threshold", 5)
    if config.get("llm_enabled", False) and rule_score >= llm_threshold:
        llm_result = await call_llm(title + "\n" + text, config.get("llm_prompt", ""))
        if llm_result:
            assessment["llm_score"] = llm_result.get("severity")
            assessment["llm_threat_type"] = llm_result.get("threat_type")
            assessment["llm_rationale"] = llm_result.get("rationale")
            # Use LLM score as final if available
            if assessment["llm_score"] is not None:
                assessment["final_score"] = assessment["llm_score"]

    # Add to feed
    threat_feed.appendleft(assessment)
    stats["threats_today"] += 1

    # Notification decision
    notify_threshold = config.get("notify_threshold", 7)
    cooldown_minutes = config.get("cooldown_minutes", 15)

    if assessment["final_score"] >= notify_threshold:
        cooldown_key = f"threat-{title[:50]}"
        now = time.time()
        last = _cooldowns.get(cooldown_key, 0)
        if now - last >= cooldown_minutes * 60:
            _cooldowns[cooldown_key] = now
            import notifier
            priority = "urgent" if assessment["final_score"] >= 9 else "high"
            used_llm = assessment["llm_score"] is not None
            tag = "[LLM]" if used_llm else "[Rule]"
            rationale = assessment.get("llm_rationale") or ""
            msg = f"{title}\n{rationale}" if rationale else title
            # Translate notification if LLM is enabled
            if config.get("llm_enabled") and ANTHROPIC_API_KEY:
                translated = await _translate_for_notify(msg)
                if translated:
                    msg = translated
            await notifier.send(
                title=f"{tag} Threat [{source}]: {assessment['final_score']}/10",
                message=msg,
                priority=priority,
                tags="warning,rotating_light",
                cooldown_key="",  # Already handled above
            )
            assessment["notified"] = True
            stats["notifications_sent"] += 1

    return assessment


def get_feed(limit: int = 100) -> list:
    """Return recent threat assessments."""
    return list(threat_feed)[:limit]


def get_stats() -> dict:
    """Return current stats."""
    _reset_daily_stats()
    return dict(stats)
