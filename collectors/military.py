"""Military aircraft tracker via OpenSky Network."""

import logging

import httpx

from collectors.base import BaseCollector
from config import (
    MILITARY_POLL_INTERVAL, OPENSKY_API_URL,
    OPENSKY_USERNAME, OPENSKY_PASSWORD,
    MONITORED_REGIONS, HTTP_TIMEOUT,
)
from ws_manager import manager

logger = logging.getLogger(__name__)

assets_cache: list[dict] = []


class MilitaryCollector(BaseCollector):
    def __init__(self):
        super().__init__("military", MILITARY_POLL_INTERVAL)

    async def collect(self):
        all_assets = []
        auth = None
        if OPENSKY_USERNAME and OPENSKY_PASSWORD:
            auth = (OPENSKY_USERNAME, OPENSKY_PASSWORD)

        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
            for region_name, region_info in MONITORED_REGIONS.items():
                bbox = region_info["bbox"]
                params = {
                    "lamin": bbox[0], "lamax": bbox[1],
                    "lomin": bbox[2], "lomax": bbox[3],
                }
                try:
                    resp = await client.get(OPENSKY_API_URL, params=params, auth=auth)
                    if resp.status_code == 200:
                        data = resp.json()
                        states = data.get("states", []) or []
                        for s in states:
                            if len(s) < 12:
                                continue
                            callsign = (s[1] or "").strip()
                            lat = s[6]
                            lon = s[5]
                            alt = s[7] or s[13]  # baro or geo altitude
                            heading = s[10]
                            on_ground = s[8]

                            if on_ground:
                                continue

                            asset = {
                                "callsign": callsign,
                                "type": "aircraft",
                                "lat": lat,
                                "lon": lon,
                                "altitude": round(alt, 0) if alt else None,
                                "heading": round(heading, 0) if heading else None,
                                "region": region_name,
                                "source": "OpenSky",
                                "icao24": s[0],
                                "origin_country": s[2],
                            }
                            all_assets.append(asset)
                    elif resp.status_code == 429:
                        logger.warning(f"[military] OpenSky rate limited for {region_name}")
                    else:
                        logger.warning(f"[military] OpenSky {region_name}: {resp.status_code}")
                except Exception as e:
                    logger.error(f"[military] OpenSky {region_name}: {e}")

        assets_cache.clear()
        assets_cache.extend(all_assets)
        await manager.broadcast("military", all_assets)
        logger.info(f"[military] Tracking {len(all_assets)} assets across {len(MONITORED_REGIONS)} regions")
        return all_assets
