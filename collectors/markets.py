"""Market data collector: Polygon.io (forex + stocks), CoinGecko, Fear & Greed."""

import asyncio
import logging
from datetime import datetime, timedelta, timezone

import httpx

from collectors.base import BaseCollector
from config import (
    MARKETS_POLL_INTERVAL,
    MARKET_SYMBOLS, FOREX_SYMBOLS, CRYPTO_IDS,
    POLYGON_API_KEY, POLYGON_PREV_CLOSE_URL, POLYGON_RANGE_URL,
    COINGECKO_PRICE_URL, COINGECKO_CHART_URL, FEAR_GREED_URL,
    HTTP_TIMEOUT, HTTP_USER_AGENT,
)
from ws_manager import manager

logger = logging.getLogger(__name__)

market_cache: dict = {
    "forex": {},
    "crypto": {},
    "stocks": {},
    "fear_greed": {"value": 50, "classification": "Neutral"},
    "intraday": {},
}

# Polygon free tier: 5 req/min -> 13s between requests
POLYGON_DELAY = 13


def _is_market_open(symbol):
    """Check if a market is currently open."""
    now = datetime.now(timezone.utc)
    weekday = now.weekday()  # 0=Mon, 6=Sun

    if symbol.startswith("C:"):
        # Forex: open Sun 17:00 ET - Fri 17:00 ET
        # In UTC: Sun 22:00 - Fri 22:00
        if weekday == 5:  # Saturday - always closed
            return False
        if weekday == 6 and now.hour < 22:  # Sunday before 22:00 UTC
            return False
        if weekday == 4 and now.hour >= 22:  # Friday after 22:00 UTC
            return False
        return True
    else:
        # US stocks: Mon-Fri 9:30-16:00 ET (14:30-21:00 UTC)
        if weekday >= 5:
            return False
        if now.hour < 14 or (now.hour == 14 and now.minute < 30):
            return False
        if now.hour >= 21:
            return False
        return True


async def _polygon_fetch_prev(client, name, symbol, target_cache):
    """Fetch prev close data from Polygon."""
    url = POLYGON_PREV_CLOSE_URL.format(ticker=symbol)
    resp = await client.get(url, params={"apiKey": POLYGON_API_KEY})
    if resp.status_code == 200:
        data = resp.json()
        results = data.get("results", [])
        if results:
            bar = results[0]
            price = bar.get("c", 0)
            open_price = bar.get("o", price)
            change = price - open_price
            change_pct = (change / open_price * 100) if open_price else 0
            decimals = 4 if ":" in symbol else 2
            is_open = _is_market_open(symbol)

            target_cache[name] = {
                "symbol": symbol,
                "name": name,
                "price": round(price, decimals),
                "change": round(change, decimals),
                "change_pct": round(change_pct, 2),
                "prev_close": round(open_price, decimals),
                "open": round(bar.get("o", 0), decimals),
                "high": round(bar.get("h", 0), decimals),
                "low": round(bar.get("l", 0), decimals),
                "volume": bar.get("v", 0),
                "is_open": is_open,
                "bar_time": bar.get("t", 0),
            }

            # Build OHLC-based intraday approximation for the single day
            # We create 4 points: open, low, high, close (positioned across the day)
            t = bar.get("t", 0)
            o, h, l, c = bar.get("o", price), bar.get("h", price), bar.get("l", price), price
            # Simulate a day's movement: open -> (dip to low or rise to high) -> close
            if abs(c - l) < abs(c - h):
                # Closed closer to low: open -> high -> low -> close
                series = [
                    {"t": t, "p": o},
                    {"t": t + 14400000, "p": h},
                    {"t": t + 43200000, "p": l},
                    {"t": t + 57600000, "p": c},
                ]
            else:
                # Closed closer to high: open -> low -> high -> close
                series = [
                    {"t": t, "p": o},
                    {"t": t + 14400000, "p": l},
                    {"t": t + 43200000, "p": h},
                    {"t": t + 57600000, "p": c},
                ]
            market_cache["intraday"][name] = series
            logger.info(f"[markets] Loaded {name}: price={price}, open={'yes' if is_open else 'CLOSED'}")
            return True
    elif resp.status_code == 429:
        logger.warning(f"[markets] Polygon rate limited for {name}")
        return False
    else:
        logger.warning(f"[markets] Polygon {name}: {resp.status_code}")
    return True


class MarketsCollector(BaseCollector):
    def __init__(self):
        super().__init__("markets", MARKETS_POLL_INTERVAL)
        self._fg_counter = 0
        self._poly_loaded = False
        self._crypto_chart_loaded = False
        self._poly_cycle = 0

    def _build_broadcast(self):
        return {
            "forex": market_cache["forex"],
            "stocks": market_cache["stocks"],
            "crypto": market_cache["crypto"],
            "fear_greed": market_cache["fear_greed"],
            "intraday": market_cache["intraday"],
        }

    async def collect(self):
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT, headers={"User-Agent": HTTP_USER_AGENT}) as client:
            # --- CoinGecko first (no rate limit, loads instantly) ---
            try:
                resp = await client.get(COINGECKO_PRICE_URL, params={
                    "ids": ",".join(CRYPTO_IDS),
                    "vs_currencies": "usd",
                    "include_24hr_change": "true",
                })
                if resp.status_code == 200:
                    data = resp.json()
                    for coin_id in CRYPTO_IDS:
                        if coin_id in data:
                            coin = data[coin_id]
                            name = coin_id.capitalize()
                            price = coin.get("usd", 0)
                            change_pct = coin.get("usd_24h_change", 0)
                            market_cache["crypto"][name] = {
                                "name": name,
                                "price": round(price, 2),
                                "change_pct": round(change_pct, 2) if change_pct else 0,
                                "is_open": True,
                            }

                # 1-day chart (~289 points, 5-min resolution)
                for coin_id in CRYPTO_IDS:
                    try:
                        name = coin_id.capitalize()
                        url = COINGECKO_CHART_URL.format(coin_id=coin_id)
                        resp2 = await client.get(url, params={
                            "vs_currency": "usd",
                            "days": "1",
                        })
                        if resp2.status_code == 200:
                            chart_data = resp2.json()
                            prices = chart_data.get("prices", [])
                            if prices:
                                series = [{"t": int(p[0]), "p": p[1]} for p in prices]
                                market_cache["intraday"][name] = series
                                if len(prices) >= 2:
                                    market_cache["crypto"][name]["prev_close"] = round(prices[0][1], 2)
                            if not self._crypto_chart_loaded:
                                logger.info(f"[markets] CoinGecko 1d chart for {name}: {len(prices)} points")
                        elif resp2.status_code == 429:
                            logger.warning(f"[markets] CoinGecko rate limited for {name}")
                        await asyncio.sleep(2)
                    except Exception as e:
                        logger.error(f"[markets] CoinGecko chart {coin_id}: {e}")
                self._crypto_chart_loaded = True

                # Broadcast crypto immediately so frontend shows them right away
                await manager.broadcast("markets", self._build_broadcast())

            except Exception as e:
                logger.error(f"[markets] CoinGecko: {e}")

            # --- Polygon (rate limited, 13s between requests) ---
            if POLYGON_API_KEY:
                all_tickers = [
                    *[(n, s, market_cache["forex"]) for n, s in FOREX_SYMBOLS.items()],
                    *[(n, s, market_cache["stocks"]) for n, s in MARKET_SYMBOLS.items()],
                ]

                if not self._poly_loaded:
                    for name, symbol, cache in all_tickers:
                        ok = await _polygon_fetch_prev(client, name, symbol, cache)
                        if not ok:
                            break
                        await manager.broadcast("markets", self._build_broadcast())
                        await asyncio.sleep(POLYGON_DELAY)
                    if market_cache["forex"] or market_cache["stocks"]:
                        self._poly_loaded = True
                else:
                    for i in range(min(2, len(all_tickers))):
                        idx = (self._poly_cycle + i) % len(all_tickers)
                        name, symbol, cache = all_tickers[idx]
                        ok = await _polygon_fetch_prev(client, name, symbol, cache)
                        if not ok:
                            break
                        await asyncio.sleep(POLYGON_DELAY)
                    self._poly_cycle = (self._poly_cycle + 2) % len(all_tickers)

            # --- Fear & Greed ---
            self._fg_counter += self.interval
            if self._fg_counter >= 900:
                self._fg_counter = 0
                try:
                    resp = await client.get(FEAR_GREED_URL)
                    if resp.status_code == 200:
                        data = resp.json()
                        fg = data.get("data", [{}])[0]
                        market_cache["fear_greed"] = {
                            "value": int(fg.get("value", 50)),
                            "classification": fg.get("value_classification", "Neutral"),
                        }
                except Exception as e:
                    logger.error(f"[markets] Fear&Greed: {e}")

        await manager.broadcast("markets", self._build_broadcast())
