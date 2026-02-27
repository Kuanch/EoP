"""Military aircraft tracker via OpenSky Network (OAuth2)."""

import asyncio
import json
import logging
import time

import httpx

from collectors.base import BaseCollector
from config import (
    MILITARY_POLL_INTERVAL, MILITARY_BROADCAST_INTERVAL, OPENSKY_API_URL,
    MONITORED_REGIONS, HTTP_TIMEOUT,
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

    async def collect(self):
        all_assets = []

        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
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
                    else:
                        logger.warning(f"[military] OpenSky {region_name}: {resp.status_code}")
                except Exception as e:
                    logger.error(f"[military] OpenSky {region_name}: {e}")

        assets_cache.clear()
        assets_cache.extend(all_assets)
        await manager.broadcast("military", all_assets)
        logger.info(f"[military] Tracking {len(all_assets)} assets across {len(MONITORED_REGIONS)} regions")
        return all_assets
