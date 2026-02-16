"""Push notifications via ntfy."""

import logging
import os
import time

import httpx

logger = logging.getLogger(__name__)

NTFY_URL = os.getenv("NTFY_URL", "http://localhost:8090")
NTFY_TOPIC = os.getenv("NTFY_TOPIC", "eop-alerts")

# Per-topic cooldown to prevent spam
_cooldowns: dict[str, float] = {}
COOLDOWN_SECONDS = 900  # 15 minutes


async def send(title: str, message: str, priority: str = "default", tags: str = "", cooldown_key: str = ""):
    """Send a push notification via ntfy.

    Args:
        title: Notification title
        message: Notification body
        priority: ntfy priority (min, low, default, high, urgent)
        tags: Comma-separated emoji tags (e.g. "warning,skull")
        cooldown_key: Unique key for cooldown dedup. If empty, no cooldown applied.
    """
    if not NTFY_URL or not NTFY_TOPIC:
        return

    # Cooldown check
    if cooldown_key:
        now = time.time()
        last = _cooldowns.get(cooldown_key, 0)
        if now - last < COOLDOWN_SECONDS:
            return
        _cooldowns[cooldown_key] = now

    url = f"{NTFY_URL}/{NTFY_TOPIC}"
    headers = {
        "Title": title,
        "Priority": priority,
    }
    if tags:
        headers["Tags"] = tags

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(url, content=message, headers=headers)
            if resp.status_code == 200:
                logger.info(f"[ntfy] Sent: {title}")
            else:
                logger.warning(f"[ntfy] HTTP {resp.status_code}: {resp.text[:200]}")
    except Exception as e:
        logger.error(f"[ntfy] Failed to send: {e}")
