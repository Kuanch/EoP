"""Polymarket geopolitical prediction markets collector."""

import logging
from datetime import datetime

import httpx

from collectors.base import BaseCollector
from config import (
    POLYMARKET_API_URL, POLYMARKET_POLL_INTERVAL, POLYMARKET_EVENTS,
    HTTP_TIMEOUT, HTTP_USER_AGENT,
)
from ws_manager import manager

logger = logging.getLogger(__name__)

polymarket_cache: list[dict] = []


class PolymarketCollector(BaseCollector):
    def __init__(self):
        super().__init__("polymarket", POLYMARKET_POLL_INTERVAL)

    async def collect(self):
        global polymarket_cache
        events = []
        async with httpx.AsyncClient(
            timeout=HTTP_TIMEOUT,
            headers={"User-Agent": HTTP_USER_AGENT},
            follow_redirects=True,
        ) as client:
            for slug in POLYMARKET_EVENTS:
                try:
                    resp = await client.get(POLYMARKET_API_URL, params={"slug": slug})
                    resp.raise_for_status()
                    data = resp.json()
                    if isinstance(data, list) and data:
                        data = data[0]
                    if not data:
                        continue

                    for market in data.get("markets", []):
                        prices = market.get("outcomePrices", "[]")
                        if isinstance(prices, str):
                            import json
                            prices = json.loads(prices)
                        yes_price = float(prices[0]) if prices else None

                        events.append({
                            "slug": market.get("slug", slug),
                            "question": market.get("question", data.get("title", "")),
                            "probability": yes_price,
                            "volume": float(market.get("volume", 0)),
                            "volume_24h": float(data.get("volume24hr", 0)),
                            "liquidity": float(data.get("liquidity", 0)),
                            "end_date": data.get("endDate"),
                            "image": data.get("icon") or data.get("image"),
                            "active": data.get("active", True),
                        })
                except Exception as e:
                    logger.warning("Polymarket fetch failed for %s: %s", slug, e)

        # Sort by probability descending
        events.sort(key=lambda x: x.get("probability", 0) or 0, reverse=True)
        polymarket_cache = events
        await manager.broadcast("polymarket", events)
        logger.info(
            "Polymarket: %d events fetched, top=%s (%.1f%%)",
            len(events),
            events[0]["slug"][:40] if events else "none",
            (events[0]["probability"] or 0) * 100 if events else 0,
        )
