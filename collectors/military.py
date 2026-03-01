"""Military aircraft tracker via OpenSky Network (OAuth2)."""

import asyncio
import json
import logging
import time

import httpx

from collectors.base import BaseCollector
from config import (
    MILITARY_POLL_INTERVAL, MILITARY_BROADCAST_INTERVAL, OPENSKY_API_URL,
    MONITORED_REGIONS, HTTP_TIMEOUT, ADSBFI_BASE_URL,
)
from ws_manager import manager

logger = logging.getLogger(__name__)

assets_cache: list[dict] = []

import os

OPENSKY_TOKEN_URL = "https://auth.opensky-network.org/auth/realms/opensky-network/protocol/openid-connect/token"
CREDENTIALS_FILE = "opensky_credentials.json"


class MilitaryCollector(BaseCollector):
    def __init__(self):
        super().__init__("military", MILITARY_POLL_INTERVAL)
        self._token = None
        self._token_expiry = 0
        self._client_id = None
        self._client_secret = None
        self._load_credentials()

    def _load_credentials(self):
        # Prefer environment variables
        self._client_id = os.getenv("OPENSKY_CLIENT_ID", "")
        self._client_secret = os.getenv("OPENSKY_CLIENT_SECRET", "")
        if self._client_id and self._client_secret:
            logger.info("[military] Loaded OpenSky credentials from environment")
            return
        # Fallback to credentials file
        try:
            with open(CREDENTIALS_FILE) as f:
                creds = json.load(f)
            self._client_id = creds.get("clientId")
            self._client_secret = creds.get("clientSecret")
            if self._client_id:
                logger.info("[military] Loaded OpenSky credentials from file")
                logger.warning("[military] Consider moving credentials to OPENSKY_CLIENT_ID / OPENSKY_CLIENT_SECRET env vars")
        except FileNotFoundError:
            logger.warning("[military] No OpenSky credentials found, using anonymous access")
        except Exception as e:
            logger.error(f"[military] Failed to load credentials: {e}")

    async def _get_token(self, client: httpx.AsyncClient) -> str | None:
        if not self._client_id:
            return None
        if self._token and time.time() < self._token_expiry - 60:
            return self._token
        try:
            resp = await client.post(OPENSKY_TOKEN_URL, data={
                "grant_type": "client_credentials",
                "client_id": self._client_id,
                "client_secret": self._client_secret,
            })
            if resp.status_code == 200:
                data = resp.json()
                self._token = data["access_token"]
                self._token_expiry = time.time() + data.get("expires_in", 1800)
                logger.info("[military] OpenSky OAuth2 token acquired")
                return self._token
            else:
                logger.warning(f"[military] OAuth2 token request failed: {resp.status_code}")
        except Exception as e:
            logger.error(f"[military] OAuth2 token error: {e}")
        return None

    async def _fetch_adsbfi(self, client: httpx.AsyncClient) -> list[dict]:
        """Fetch all aircraft from adsb.fi per-region using lat/lon/dist endpoint."""
        assets = []
        for i, (region_name, region_info) in enumerate(MONITORED_REGIONS.items()):
            if i > 0:
                await asyncio.sleep(1)  # adsb.fi rate limit: 1 req/sec
            center = region_info["center"]
            url = ADSBFI_BASE_URL.format(lat=center[0], lon=center[1], dist=250)
            try:
                resp = await client.get(url, timeout=HTTP_TIMEOUT)
                if resp.status_code == 200:
                    data = resp.json()
                    aircraft_list = data.get("ac", [])
                    for ac in aircraft_list:
                        lat = ac.get("lat")
                        lon = ac.get("lon")
                        if lat is None or lon is None:
                            continue
                        alt_baro = ac.get("alt_baro")
                        if alt_baro == "ground":
                            continue
                        # Filter to bounding box (circle may extend beyond)
                        bbox = region_info["bbox"]
                        if not (bbox[0] <= lat <= bbox[1] and bbox[2] <= lon <= bbox[3]):
                            continue
                        callsign = (ac.get("flight") or "").strip()
                        alt = ac.get("alt_geom") or (alt_baro if isinstance(alt_baro, (int, float)) else None)
                        # Convert feet to meters to match OpenSky format
                        alt_meters = round(alt * 0.3048, 0) if alt else None
                        heading = ac.get("track")
                        assets.append({
                            "callsign": callsign,
                            "type": "aircraft",
                            "lat": lat,
                            "lon": lon,
                            "altitude": alt_meters,
                            "heading": round(heading, 0) if heading else None,
                            "region": region_name,
                            "source": "adsb.fi",
                            "icao24": ac.get("hex", "").lower(),
                            "origin_country": ac.get("ownOp") or ac.get("r") or "",
                        })
                elif resp.status_code == 429:
                    logger.warning(f"[military] adsb.fi rate limited for {region_name}")
                else:
                    logger.warning(f"[military] adsb.fi {region_name}: {resp.status_code}")
            except Exception as e:
                logger.error(f"[military] adsb.fi {region_name}: {e}")
        logger.info(f"[military] adsb.fi returned {len(assets)} aircraft in monitored regions")
        return assets

    @staticmethod
    def _find_region(lat: float, lon: float) -> str | None:
        """Return the name of the monitored region containing this lat/lon, or None."""
        for name, info in MONITORED_REGIONS.items():
            bbox = info["bbox"]
            if bbox[0] <= lat <= bbox[1] and bbox[2] <= lon <= bbox[3]:
                return name
        return None

    async def run(self):
        """Start both the collector loop and a faster broadcast loop."""
        asyncio.create_task(self._broadcast_loop())
        await super().run()

    async def _broadcast_loop(self):
        """Re-broadcast cached aircraft positions every MILITARY_BROADCAST_INTERVAL seconds."""
        while self._running:
            await asyncio.sleep(MILITARY_BROADCAST_INTERVAL)
            try:
                if assets_cache:
                    await manager.broadcast("military", list(assets_cache))
            except Exception as e:
                logger.error(f"[military] broadcast error: {e}")

    async def _fetch_opensky(self, client: httpx.AsyncClient) -> list[dict]:
        """Fetch aircraft from OpenSky Network per-region bounding boxes."""
        assets = []
        token = await self._get_token(client)
        headers = {"Authorization": f"Bearer {token}"} if token else {}

        for i, (region_name, region_info) in enumerate(MONITORED_REGIONS.items()):
            if i > 0:
                await asyncio.sleep(5)
            bbox = region_info["bbox"]
            params = {
                "lamin": bbox[0], "lamax": bbox[1],
                "lomin": bbox[2], "lomax": bbox[3],
            }
            try:
                resp = await client.get(OPENSKY_API_URL, params=params, headers=headers)
                if resp.status_code == 429:
                    logger.warning(f"[military] OpenSky rate limited for {region_name}, retrying in 10s")
                    await asyncio.sleep(10)
                    resp = await client.get(OPENSKY_API_URL, params=params, headers=headers)
                if resp.status_code == 200:
                    data = resp.json()
                    states = data.get("states", []) or []
                    for s in states:
                        if len(s) < 12:
                            continue
                        callsign = (s[1] or "").strip()
                        lat = s[6]
                        lon = s[5]
                        alt = s[7] or s[13]
                        heading = s[10]
                        on_ground = s[8]

                        if on_ground:
                            continue

                        assets.append({
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
                        })
                else:
                    logger.warning(f"[military] OpenSky {region_name}: {resp.status_code}")
            except Exception as e:
                logger.error(f"[military] OpenSky {region_name}: {e}")
        return assets

    async def collect(self):
        all_assets = []

        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
            # Fetch from both sources concurrently
            opensky_task = asyncio.create_task(self._fetch_opensky(client))
            adsbfi_task = asyncio.create_task(self._fetch_adsbfi(client))

            opensky_assets = await opensky_task
            adsbfi_assets = await adsbfi_task

            # Merge: deduplicate by icao24, adsb.fi takes priority (richer metadata)
            seen = {}
            for asset in adsbfi_assets:
                icao = asset.get("icao24", "").lower()
                if icao:
                    seen[icao] = asset
            for asset in opensky_assets:
                icao = asset.get("icao24", "").lower()
                if icao and icao not in seen:
                    seen[icao] = asset
            all_assets = list(seen.values())

        assets_cache.clear()
        assets_cache.extend(all_assets)
        await manager.broadcast("military", all_assets)
        logger.info(f"[military] Tracking {len(all_assets)} assets across {len(MONITORED_REGIONS)} regions (OpenSky: {len(opensky_assets)}, adsb.fi: {len(adsbfi_assets)})")
        return all_assets
