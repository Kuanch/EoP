"""Market data collector: Polygon.io (forex + stocks), CoinGecko, Fear & Greed."""

import asyncio
import logging
from collections import defaultdict
from datetime import datetime, timedelta, timezone

import httpx

from collectors.base import BaseCollector
from config import (
    MARKETS_POLL_INTERVAL, FEAR_GREED_POLL_INTERVAL,
    MARKET_SYMBOLS, FOREX_SYMBOLS, CRYPTO_IDS,
    POLYGON_API_KEY, POLYGON_PREV_CLOSE_URL, POLYGON_RANGE_URL,
    COINGECKO_PRICE_URL, COINGECKO_CHART_URL, FEAR_GREED_URL,
    HTTP_TIMEOUT, HTTP_USER_AGENT,
)
from ws_manager import manager

logger = logging.getLogger(__name__)

market_cache: dict = {
    "forex": {},      # EUR/USD etc - primary
    "crypto": {},     # BTC, ETH - primary
    "stocks": {},     # SPY, QQQ etc - secondary
    "fear_greed": {"value": 50, "classification": "Neutral"},
    "intraday": {},   # all chart series
    "history": defaultdict(list),
}
MAX_HISTORY = 50

# Polygon free tier: 5 req/min -> 13s between requests
POLYGON_DELAY = 13


async def _polygon_fetch_chart(client, name, symbol, cache_key, target_cache, month_ago, today):
    """Fetch 30-day daily bars from Polygon for a single ticker."""
    url = POLYGON_RANGE_URL.format(
        ticker=symbol, multiplier=1, timespan="day",
        from_date=month_ago, to_date=today,
    )
    resp = await client.get(url, params={"apiKey": POLYGON_API_KEY, "adjusted": "true", "sort": "asc"})
    if resp.status_code == 200:
        data = resp.json()
        bars = data.get("results", [])
        if bars:
            series = [{"t": b["t"], "p": b["c"]} for b in bars if "t" in b and "c" in b]
            market_cache["intraday"][name] = series

            latest = bars[-1]
            prev = bars[-2] if len(bars) > 1 else bars[-1]
            price = latest.get("c", 0)
            prev_close = prev.get("c", price)
            change = price - prev_close
            change_pct = (change / prev_close * 100) if prev_close else 0

            # Forex needs more decimal places
            decimals = 4 if ":" in symbol else 2

            target_cache[name] = {
                "symbol": symbol,
                "name": name,
                "price": round(price, decimals),
                "change": round(change, decimals),
                "change_pct": round(change_pct, 2),
                "prev_close": round(prev_close, decimals),
                "high": round(latest.get("h", 0), decimals),
                "low": round(latest.get("l", 0), decimals),
                "volume": latest.get("v", 0),
            }
            logger.info(f"[markets] Loaded {name}: {len(bars)} bars, price={price}")
            return True
    elif resp.status_code == 429:
        logger.warning(f"[markets] Polygon rate limited for {name}")
        return False  # signal to stop
    else:
        logger.warning(f"[markets] Polygon {name}: {resp.status_code}")
    return True  # continue to next


async def _polygon_fetch_prev(client, name, symbol, target_cache):
    """Fetch prev close from Polygon for updates."""
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

            target_cache[name] = {
                **target_cache.get(name, {}),
                "symbol": symbol,
                "name": name,
                "price": round(price, decimals),
                "change": round(change, decimals),
                "change_pct": round(change_pct, 2),
                "prev_close": round(open_price, decimals),
                "high": round(bar.get("h", 0), decimals),
                "low": round(bar.get("l", 0), decimals),
                "volume": bar.get("v", 0),
            }
            # Append to chart series
            series = market_cache["intraday"].get(name, [])
            if series and series[-1]["t"] != bar.get("t"):
                series.append({"t": bar.get("t", 0), "p": price})
                market_cache["intraday"][name] = series[-60:]
            return True
    elif resp.status_code == 429:
        logger.warning(f"[markets] Polygon rate limited")
        return False
    return True


class MarketsCollector(BaseCollector):
    def __init__(self):
        super().__init__("markets", MARKETS_POLL_INTERVAL)
        self._fg_counter = 0
        self._chart_loaded = False
        self._crypto_chart_loaded = False

    async def collect(self):
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT, headers={"User-Agent": HTTP_USER_AGENT}) as client:
            if POLYGON_API_KEY:
                now = datetime.now(timezone.utc)
                today = now.strftime("%Y-%m-%d")
                month_ago = (now - timedelta(days=30)).strftime("%Y-%m-%d")

                if not self._chart_loaded:
                    # First run: load 30-day charts for all Polygon tickers
                    # Forex first (primary), then stocks (secondary)
                    all_tickers = [
                        *[(n, s, market_cache["forex"]) for n, s in FOREX_SYMBOLS.items()],
                        *[(n, s, market_cache["stocks"]) for n, s in MARKET_SYMBOLS.items()],
                    ]
                    for name, symbol, cache in all_tickers:
                        ok = await _polygon_fetch_chart(client, name, symbol, name, cache, month_ago, today)
                        if not ok:
                            break  # rate limited, retry next cycle
                        await asyncio.sleep(POLYGON_DELAY)

                    if market_cache["forex"] or market_cache["stocks"]:
                        self._chart_loaded = True
                else:
                    # Subsequent runs: rotate through tickers (1-2 per cycle to stay under rate limit)
                    all_tickers = [
                        *[(n, s, market_cache["forex"]) for n, s in FOREX_SYMBOLS.items()],
                        *[(n, s, market_cache["stocks"]) for n, s in MARKET_SYMBOLS.items()],
                    ]
                    # Update 2 tickers per 60s cycle
                    cycle = int(now.timestamp() / self.interval) % len(all_tickers)
                    for i in range(min(2, len(all_tickers))):
                        idx = (cycle + i) % len(all_tickers)
                        name, symbol, cache = all_tickers[idx]
                        ok = await _polygon_fetch_prev(client, name, symbol, cache)
                        if not ok:
                            break
                        await asyncio.sleep(POLYGON_DELAY)

            # Crypto from CoinGecko
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
                            }

                if not self._crypto_chart_loaded:
                    for coin_id in CRYPTO_IDS:
                        try:
                            name = coin_id.capitalize()
                            url = COINGECKO_CHART_URL.format(coin_id=coin_id)
                            resp2 = await client.get(url, params={
                                "vs_currency": "usd",
                                "days": "30",
                                "interval": "daily",
                            })
                            if resp2.status_code == 200:
                                chart_data = resp2.json()
                                prices = chart_data.get("prices", [])
                                if prices:
                                    series = [{"t": int(p[0]), "p": p[1]} for p in prices]
                                    market_cache["intraday"][name] = series
                                    if len(prices) >= 2:
                                        market_cache["crypto"][name]["prev_close"] = round(prices[-2][1], 2)
                                logger.info(f"[markets] CoinGecko chart loaded for {name}: {len(prices)} points")
                            elif resp2.status_code == 429:
                                logger.warning(f"[markets] CoinGecko rate limited for {name}")
                            await asyncio.sleep(2)
                        except Exception as e:
                            logger.error(f"[markets] CoinGecko chart {coin_id}: {e}")
                    self._crypto_chart_loaded = True
                else:
                    for coin_id in CRYPTO_IDS:
                        name = coin_id.capitalize()
                        if name in market_cache["crypto"] and name in market_cache["intraday"]:
                            series = market_cache["intraday"][name]
                            now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
                            price = market_cache["crypto"][name]["price"]
                            if series and (now_ms - series[-1]["t"]) > 3600000:
                                series.append({"t": now_ms, "p": price})
                                market_cache["intraday"][name] = series[-60:]

            except Exception as e:
                logger.error(f"[markets] CoinGecko: {e}")

            # Fear & Greed
            self._fg_counter += self.interval
            if self._fg_counter >= FEAR_GREED_POLL_INTERVAL:
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

        broadcast_data = {
            "forex": market_cache["forex"],
            "stocks": market_cache["stocks"],
            "crypto": market_cache["crypto"],
            "fear_greed": market_cache["fear_greed"],
            "intraday": market_cache["intraday"],
            "history": {k: list(v) for k, v in market_cache["history"].items()},
        }
        await manager.broadcast("markets", broadcast_data)
        return broadcast_data
