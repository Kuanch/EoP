"""Market data collector: Finnhub (stocks), Polygon (forex), CoinGecko (crypto), Fear & Greed."""

import asyncio
import json
import logging
import os
from datetime import datetime, timedelta, timezone

import httpx

from collectors.base import BaseCollector
from config import (
    MARKETS_POLL_INTERVAL,
    FOREX_SYMBOLS, CRYPTO_IDS,
    POLYGON_API_KEY, POLYGON_PREV_CLOSE_URL, POLYGON_RANGE_URL,
    FINNHUB_API_KEY, FINNHUB_QUOTE_URL, FINNHUB_STOCK_SYMBOLS,
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

# Max intraday points to keep per instrument (48h at 1-min = 2880, keep 2 days)
MAX_INTRADAY_POINTS = 2880

# Persistent storage for stock intraday data
STOCK_DATA_FILE = "data/stock_intraday.json"


def _load_stock_history():
    """Load persistent stock intraday data from disk."""
    if not os.path.exists(STOCK_DATA_FILE):
        return {}

    try:
        with open(STOCK_DATA_FILE, 'r') as f:
            data = json.load(f)

        # Clean old data (older than 3 days)
        cutoff_time = int((datetime.now(timezone.utc) - timedelta(days=3)).timestamp() * 1000)
        cleaned_data = {}

        for symbol, series in data.items():
            cleaned_series = [point for point in series if point.get("t", 0) > cutoff_time]
            if cleaned_series:
                cleaned_data[symbol] = cleaned_series

        logger.info(f"[markets] Loaded stock history: {list(cleaned_data.keys())}")
        return cleaned_data
    except Exception as e:
        logger.error(f"[markets] Failed to load stock history: {e}")
        return {}


def _save_stock_history(stock_data):
    """Save stock intraday data to disk."""
    try:
        os.makedirs(os.path.dirname(STOCK_DATA_FILE), exist_ok=True)
        with open(STOCK_DATA_FILE, 'w') as f:
            json.dump(stock_data, f)
    except Exception as e:
        logger.error(f"[markets] Failed to save stock history: {e}")


def _is_forex_open():
    """Check if forex market is currently open."""
    now = datetime.now(timezone.utc)
    weekday = now.weekday()
    if weekday == 5:
        return False
    if weekday == 6 and now.hour < 22:
        return False
    if weekday == 4 and now.hour >= 22:
        return False
    return True


def _is_stock_open():
    """Check if US stock market is currently open."""
    now = datetime.now(timezone.utc)
    weekday = now.weekday()
    if weekday >= 5:
        return False
    if now.hour < 14 or (now.hour == 14 and now.minute < 30):
        return False
    if now.hour >= 21:
        return False
    return True


# --- Finnhub (stocks: real-time quotes, accumulated into intraday series) ---

async def _finnhub_fetch_quote(client, name, finnhub_symbol):
    """Fetch real-time quote from Finnhub and accumulate intraday point."""
    resp = await client.get(FINNHUB_QUOTE_URL, params={
        "symbol": finnhub_symbol,
        "token": FINNHUB_API_KEY,
    })
    if resp.status_code == 200:
        data = resp.json()
        price = data.get("c", 0)
        if not price:
            return True

        prev_close = data.get("pc", price)
        change = data.get("d", 0)
        change_pct = data.get("dp", 0)
        is_open = _is_stock_open()

        market_cache["stocks"][name] = {
            "symbol": finnhub_symbol,
            "name": name,
            "price": round(price, 2),
            "change": round(change, 2),
            "change_pct": round(change_pct, 2),
            "prev_close": round(prev_close, 2),
            "open": round(data.get("o", 0), 2),
            "high": round(data.get("h", 0), 2),
            "low": round(data.get("l", 0), 2),
            "is_open": is_open,
        }

        # Accumulate intraday data point (only during market hours)
        if name not in market_cache["intraday"]:
            market_cache["intraday"][name] = []
        series = market_cache["intraday"][name]

        if is_open:
            now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
            # Only add if price changed or enough time passed (>= 30s)
            if not series or (now_ms - series[-1]["t"] >= 30000):
                series.append({"t": now_ms, "p": price})
                # Trim to max points
                if len(series) > MAX_INTRADAY_POINTS:
                    market_cache["intraday"][name] = series[-MAX_INTRADAY_POINTS:]

        logger.debug(f"[markets] Finnhub {name}: {price} ({len(series)} pts)")
        return True
    elif resp.status_code == 429:
        logger.warning(f"[markets] Finnhub rate limited for {name}")
        return False
    else:
        logger.warning(f"[markets] Finnhub {name}: {resp.status_code}")
    return True


# --- Polygon (forex only: prev-close + range) ---

async def _polygon_fetch_prev(client, name, symbol):
    """Fetch prev close data from Polygon for forex."""
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
            is_open = _is_forex_open()

            market_cache["forex"][name] = {
                "symbol": symbol,
                "name": name,
                "price": round(price, 4),
                "change": round(change, 4),
                "change_pct": round(change_pct, 2),
                "prev_close": round(open_price, 4),
                "open": round(bar.get("o", 0), 4),
                "high": round(bar.get("h", 0), 4),
                "low": round(bar.get("l", 0), 4),
                "volume": bar.get("v", 0),
                "is_open": is_open,
            }

            # OHLC fallback if no range data yet
            if name not in market_cache["intraday"] or len(market_cache["intraday"].get(name, [])) < 2:
                t = bar.get("t", 0)
                o, h, l, c = bar.get("o", price), bar.get("h", price), bar.get("l", price), price
                if abs(c - l) < abs(c - h):
                    series = [{"t": t, "p": o}, {"t": t + 14400000, "p": h},
                              {"t": t + 43200000, "p": l}, {"t": t + 57600000, "p": c}]
                else:
                    series = [{"t": t, "p": o}, {"t": t + 14400000, "p": l},
                              {"t": t + 43200000, "p": h}, {"t": t + 57600000, "p": c}]
                market_cache["intraday"][name] = series

            logger.info(f"[markets] Polygon {name}: {price}, {'open' if is_open else 'CLOSED'}")
            return True
    elif resp.status_code == 429:
        logger.warning(f"[markets] Polygon rate limited for {name}")
        return False
    else:
        logger.warning(f"[markets] Polygon {name}: {resp.status_code}")
    return True


async def _polygon_fetch_range(client, name, symbol):
    """Fetch 24h of 5-minute bars from Polygon range API for forex."""
    now = datetime.now(timezone.utc)
    from_ts = int((now - timedelta(hours=24)).timestamp() * 1000)
    to_ts = int(now.timestamp() * 1000)
    url = POLYGON_RANGE_URL.format(
        ticker=symbol, multiplier=5, timespan="minute",
        from_date=from_ts, to_date=to_ts,
    )
    resp = await client.get(url, params={"apiKey": POLYGON_API_KEY, "limit": 5000})
    if resp.status_code == 200:
        data = resp.json()
        results = data.get("results", [])
        if results:
            series = [{"t": bar["t"], "p": bar["c"]} for bar in results]
            market_cache["intraday"][name] = series
            logger.info(f"[markets] Range {name}: {len(series)} points (24h/5min)")
            return True
    elif resp.status_code == 429:
        logger.warning(f"[markets] Polygon range rate limited for {name}")
        return False
    else:
        logger.warning(f"[markets] Polygon range {name}: {resp.status_code}")
    return True


class MarketsCollector(BaseCollector):
    def __init__(self):
        super().__init__("markets", MARKETS_POLL_INTERVAL)
        self._fg_counter = 0
        self._poly_loaded = False
        self._range_loaded = False
        self._crypto_chart_loaded = False
        self._poly_cycle = 0

        # Load historical stock data
        historical_stocks = _load_stock_history()
        for symbol, series in historical_stocks.items():
            market_cache["intraday"][symbol] = series

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

                await manager.broadcast("markets", self._build_broadcast())

            except Exception as e:
                logger.error(f"[markets] CoinGecko: {e}")

            # --- Finnhub (stocks: real-time quotes, no rate limit issues) ---
            if FINNHUB_API_KEY:
                for name, symbol in FINNHUB_STOCK_SYMBOLS.items():
                    await _finnhub_fetch_quote(client, name, symbol)
                    await asyncio.sleep(0.5)  # Small delay to be nice
                await manager.broadcast("markets", self._build_broadcast())

            # --- Polygon (forex only, rate limited) ---
            if POLYGON_API_KEY:
                forex_tickers = [(n, s) for n, s in FOREX_SYMBOLS.items()]

                if not self._poly_loaded:
                    for name, symbol in forex_tickers:
                        ok = await _polygon_fetch_prev(client, name, symbol)
                        if not ok:
                            break
                        await manager.broadcast("markets", self._build_broadcast())
                        await asyncio.sleep(POLYGON_DELAY)
                    if market_cache["forex"]:
                        self._poly_loaded = True
                elif not self._range_loaded:
                    for name, symbol in forex_tickers:
                        ok = await _polygon_fetch_range(client, name, symbol)
                        if not ok:
                            break
                        await manager.broadcast("markets", self._build_broadcast())
                        await asyncio.sleep(POLYGON_DELAY)
                    self._range_loaded = True
                else:
                    # Steady state: rotate forex tickers (prev + range)
                    idx = self._poly_cycle % len(forex_tickers)
                    name, symbol = forex_tickers[idx]
                    ok = await _polygon_fetch_prev(client, name, symbol)
                    if ok:
                        await asyncio.sleep(POLYGON_DELAY)
                        await _polygon_fetch_range(client, name, symbol)
                    self._poly_cycle = (self._poly_cycle + 1) % len(forex_tickers)

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

        # Save stock data to disk periodically
        stock_data = {name: series for name, series in market_cache["intraday"].items()
                     if name in FINNHUB_STOCK_SYMBOLS}
        if stock_data:
            _save_stock_history(stock_data)

        await manager.broadcast("markets", self._build_broadcast())
