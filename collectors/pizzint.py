"""PizzINT collector: Pentagon Pizza Index from pizzint.watch."""

import json
import logging
import re
from datetime import datetime

import httpx

from collectors.base import BaseCollector
from config import HTTP_TIMEOUT, HTTP_USER_AGENT
from ws_manager import manager

logger = logging.getLogger(__name__)

PIZZINT_URL = "https://www.pizzint.watch/"
PIZZINT_POLL_INTERVAL = 300  # 5 minutes

pizzint_cache: dict = {
    "optempo_level": None,
    "optempo_label": None,
    "assessment": None,
    "metro_ratio": None,
    "corridors": [],
    "polymarket": [],
    "timestamp": None,
}


class PizzIntCollector(BaseCollector):
    def __init__(self):
        super().__init__("pizzint", PIZZINT_POLL_INTERVAL)

    async def collect(self):
        global pizzint_cache
        async with httpx.AsyncClient(
            timeout=HTTP_TIMEOUT,
            headers={"User-Agent": HTTP_USER_AGENT},
            follow_redirects=True,
        ) as client:
            resp = await client.get(PIZZINT_URL)
            resp.raise_for_status()
            html = resp.text

        # Extract __NEXT_DATA__ JSON from the page
        data = self._extract_next_data(html)
        if not data:
            # Fallback: parse raw HTML for key indicators
            data = self._extract_from_html(html)

        if data:
            old_level = pizzint_cache.get("optempo_level")
            pizzint_cache.update(data)
            pizzint_cache["timestamp"] = datetime.utcnow().isoformat()
            await manager.broadcast("pizzint", pizzint_cache)
            logger.info(
                "PizzINT: OPTEMPO Level %s (%s)",
                pizzint_cache.get("optempo_level"),
                pizzint_cache.get("optempo_label"),
            )

            # Threat engine assessment on level change
            new_level = pizzint_cache.get("optempo_level")
            if old_level is not None and new_level is not None and new_level != old_level:
                import threat_engine
                try:
                    await threat_engine.assess(
                        "pizzint",
                        f"OPTEMPO Level {new_level} ({pizzint_cache.get('optempo_label', '')})",
                        f"Changed from level {old_level}. {pizzint_cache.get('assessment', '')}",
                    )
                except Exception as e:
                    logger.error(f"[pizzint] Threat assess error: {e}")

    def _extract_next_data(self, html: str) -> dict | None:
        """Extract data from React Server Components payload (double-escaped JSON in __next_f.push)."""
        # The RSC payload uses double-escaped JSON: \\" instead of "
        # First unescape to get standard JSON
        unescaped = html.replace('\\"', '"').replace('\\\\', '\\')
        result = {}

        # Extract OPTEMPO block
        optempo_match = re.search(
            r'"optempo"\s*:\s*\{[^}]*"level"\s*:\s*(\d+)[^}]*"label"\s*:\s*"([^"]*)"',
            unescaped,
        )
        if not optempo_match:
            # Try reversed order (label before level)
            optempo_match = re.search(
                r'"optempo"\s*:\s*\{[^}]*"label"\s*:\s*"([^"]*)"[^}]*"level"\s*:\s*(\d+)',
                unescaped,
            )
            if optempo_match:
                result["optempo_label"] = optempo_match.group(1)
                result["optempo_level"] = int(optempo_match.group(2))
        else:
            result["optempo_level"] = int(optempo_match.group(1))
            result["optempo_label"] = optempo_match.group(2)

        # OPTEMPO color
        color_match = re.search(r'"optempo"\s*:\s*\{[^}]*"color"\s*:\s*"([^"]*)"', unescaped)
        if color_match:
            result["optempo_color"] = color_match.group(1)

        # Assessment text
        assess_match = re.search(r'"assessment"\s*:\s*"([^"]{20,})"', unescaped)
        if assess_match:
            result["assessment"] = assess_match.group(1)

        # Metro/popularity ratio
        metro_match = re.search(r'"popularityRatio"\s*:\s*([\d.]+)', unescaped)
        if metro_match:
            result["metro_ratio"] = float(metro_match.group(1))

        # Corridor speed data
        corridors = []
        for m in re.finditer(
            r'\{"id"\s*:\s*"([^"]+)"\s*,\s*"tier"\s*:\s*(\d+)\s*,\s*"deviation"\s*:\s*([-\d.]+)\s*,\s*"speedRatio"\s*:\s*([\d.]+)',
            unescaped,
        ):
            corridors.append({
                "id": m.group(1),
                "tier": int(m.group(2)),
                "deviation": float(m.group(3)),
                "speed_ratio": float(m.group(4)),
            })
        if corridors:
            result["corridors"] = corridors

        # Polymarket geopolitical odds
        markets = []
        for m in re.finditer(
            r'\{"slug"\s*:\s*"([^"]+)"\s*,\s*"label"\s*:\s*"([^"]+)"[^}]*?"price"\s*:\s*([\d.]+)',
            unescaped,
        ):
            markets.append({
                "slug": m.group(1),
                "label": m.group(2),
                "probability": float(m.group(3)),
            })
        if markets:
            result["polymarket"] = markets

        return result if result else None

    def _extract_from_html(self, html: str) -> dict | None:
        """Fallback: extract key data directly from HTML text."""
        result = {}

        # OPTEMPO level
        level_match = re.search(r'(?:OPTEMPO|Level)\s*[:\s]*(\d)', html, re.IGNORECASE)
        if level_match:
            result["optempo_level"] = int(level_match.group(1))

        # Labels like "Business As Usual", "Elevated", "High Alert"
        label_match = re.search(
            r'(Business As Usual|Elevated Activity|High Alert|Critical|DEFCON)',
            html,
            re.IGNORECASE,
        )
        if label_match:
            result["optempo_label"] = label_match.group(1)

        # Assessment text
        assess_match = re.search(
            r'(?:assessment|Traffic patterns)[^"<]*?([A-Z][^<"]{20,200})',
            html,
            re.IGNORECASE,
        )
        if assess_match:
            result["assessment"] = assess_match.group(1).strip()

        return result if result else None
