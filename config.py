"""Centralized configuration for Eye of Providence."""

import os

# Polling intervals (seconds)
NEWS_POLL_INTERVAL = 300       # 5 minutes
MARKETS_POLL_INTERVAL = 60     # 1 minute
MILITARY_POLL_INTERVAL = 30    # 30 seconds
CYBER_POLL_INTERVAL = 1800     # 30 minutes
SHIPS_BROADCAST_INTERVAL = 5   # 5 seconds (batch AIS updates)

# API Keys (from environment)
OTX_API_KEY = os.getenv("OTX_API_KEY", "")
POLYGON_API_KEY = os.getenv("POLYGON_API_KEY", "")
FINNHUB_API_KEY = os.getenv("FINNHUB_API_KEY", "")
AISSTREAM_API_KEY = os.getenv("AISSTREAM_API_KEY", "")
# OpenSky credentials now loaded from opensky_credentials.json (OAuth2)

# News RSS Feeds
NEWS_FEEDS = {
    "BBC World": "https://feeds.bbci.co.uk/news/world/rss.xml",
    "Al Jazeera": "https://www.aljazeera.com/xml/rss/all.xml",
    "CNA World": "https://feeds.feedburner.com/rsscna/intworld",
    "CNA Mainland": "https://feeds.feedburner.com/rsscna/mainland",
    "CBS World": "https://www.cbsnews.com/latest/rss/world",
}

# Market symbols
# Forex pairs (primary monitors)
FOREX_SYMBOLS = {
    "EUR/USD": "C:EURUSD",
    "USD/JPY": "C:USDJPY",
}

CRYPTO_IDS = ["bitcoin"]

# Finnhub: free tier supports real-time US stock quotes only
# Forex stays on Polygon (delayed but functional)
FINNHUB_STOCK_SYMBOLS = {
    "S&P 500": "SPY",
    "NASDAQ": "QQQ",
    "Gold": "GLD",
}

# CoinGecko
COINGECKO_PRICE_URL = "https://api.coingecko.com/api/v3/simple/price"
COINGECKO_CHART_URL = "https://api.coingecko.com/api/v3/coins/{coin_id}/market_chart"

# Fear & Greed
FEAR_GREED_URL = "https://api.alternative.me/fng/"

# Polygon.io
POLYGON_BASE_URL = "https://api.polygon.io"
POLYGON_PREV_CLOSE_URL = f"{POLYGON_BASE_URL}/v2/aggs/ticker/{{ticker}}/prev"
POLYGON_RANGE_URL = f"{POLYGON_BASE_URL}/v2/aggs/ticker/{{ticker}}/range/{{multiplier}}/{{timespan}}/{{from_date}}/{{to_date}}"

# Finnhub
FINNHUB_BASE_URL = "https://finnhub.io/api/v1"
FINNHUB_QUOTE_URL = f"{FINNHUB_BASE_URL}/quote"

# OpenSky Network
OPENSKY_API_URL = "https://opensky-network.org/api/states/all"

# adsb.fi Open Data API (free, no auth required)
ADSBFI_BASE_URL = "https://opendata.adsb.fi/api/v3/lat/{lat}/lon/{lon}/dist/{dist}"

# Monitored regions (bounding boxes: lat_min, lat_max, lon_min, lon_max)
MONITORED_REGIONS = {
    "Taiwan Strait": {"bbox": [21.0, 27.0, 116.0, 123.0], "center": [24.0, 119.5]},
    "East Ukraine": {"bbox": [46.0, 52.0, 32.0, 40.0], "center": [49.0, 36.0]},
    "Middle East": {"bbox": [28.0, 38.0, 33.0, 55.0], "center": [33.0, 44.0]},
    "Korean Peninsula": {"bbox": [33.0, 43.0, 124.0, 132.0], "center": [38.0, 127.0]},
    "South China Sea": {"bbox": [5.0, 22.0, 105.0, 121.0], "center": [13.0, 113.0]},
}

# Cyber sources
CISA_KEV_URL = "https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json"
FEODO_URL = "https://feodotracker.abuse.ch/downloads/ipblocklist.json"
OTX_PULSE_URL = "https://otx.alienvault.com/api/v1/pulses/subscribed"
URLHAUS_CSV_URL = "https://urlhaus.abuse.ch/downloads/csv_recent/"
C2INTEL_CSV_URL = "https://raw.githubusercontent.com/drb-ra/C2IntelFeeds/master/feeds/IPC2s-30day.csv"

# Geo-tagging keyword → region mapping
GEO_KEYWORDS = {
    "Taiwan": (24.0, 121.0, "Taiwan Strait"),
    "Taipei": (25.03, 121.56, "Taiwan Strait"),
    "China": (35.0, 105.0, "East Asia"),
    "Beijing": (39.9, 116.4, "East Asia"),
    "Shanghai": (31.2, 121.5, "East Asia"),
    "Ukraine": (49.0, 32.0, "East Ukraine"),
    "Kyiv": (50.45, 30.52, "East Ukraine"),
    "Kharkiv": (49.99, 36.23, "East Ukraine"),
    "Russia": (55.75, 37.62, "Russia"),
    "Moscow": (55.75, 37.62, "Russia"),
    "Israel": (31.77, 35.22, "Middle East"),
    "Gaza": (31.35, 34.31, "Middle East"),
    "Iran": (35.69, 51.39, "Middle East"),
    "Iraq": (33.3, 44.37, "Middle East"),
    "Syria": (33.51, 36.29, "Middle East"),
    "Lebanon": (33.89, 35.50, "Middle East"),
    "Yemen": (15.35, 44.21, "Middle East"),
    "North Korea": (39.02, 125.75, "Korean Peninsula"),
    "South Korea": (37.57, 126.98, "Korean Peninsula"),
    "Seoul": (37.57, 126.98, "Korean Peninsula"),
    "Pyongyang": (39.02, 125.75, "Korean Peninsula"),
    "Philippines": (14.6, 120.98, "South China Sea"),
    "Vietnam": (21.03, 105.85, "South China Sea"),
    "Japan": (35.68, 139.69, "East Asia"),
    "Tokyo": (35.68, 139.69, "East Asia"),
    "India": (28.61, 77.21, "South Asia"),
    "Pakistan": (33.69, 73.04, "South Asia"),
    "Afghanistan": (34.53, 69.17, "Central Asia"),
    "Libya": (32.90, 13.18, "North Africa"),
    "Sudan": (15.50, 32.56, "East Africa"),
    "Somalia": (2.05, 45.32, "East Africa"),
    "NATO": (50.85, 4.35, "Europe"),
    "Pentagon": (38.87, -77.06, "North America"),
    "missile": None,
    "nuclear": None,
    "military": None,
    "troops": None,
    "airstrike": None,
    "bombing": None,
    "invasion": None,
    "war": None,
}

# Polymarket - Geopolitical prediction markets
POLYMARKET_API_URL = "https://gamma-api.polymarket.com/events"
POLYMARKET_POLL_INTERVAL = 300  # 5 minutes
POLYMARKET_EVENTS = [
    "will-china-invade-taiwan-before-2027",
    "us-x-china-military-clash-before-2027",
    "will-north-korea-invade-south-korea-before-2027",
    "us-x-russia-military-clash-by-june-30-2026-249",
    "will-the-us-invade-a-latin-american-country-in-2026",
    "us-civil-war-before-2027",
    "nuclear-weapon-detonation-by-march-31",
]

# AISstream WebSocket
AISSTREAM_WS_URL = "wss://stream.aisstream.io/v0/stream"

# Ship tracking regions (lat/lon pairs for AISstream bounding boxes)
SHIP_REGIONS = {
    "Taiwan Strait": [[21.0, 116.0], [27.0, 123.0]],
    "Singapore Strait": [[0.0, 100.0], [5.0, 108.0]],
    "English Channel": [[49.0, -5.0], [52.0, 3.0]],
}

# HTTP request settings
HTTP_TIMEOUT = 30
HTTP_USER_AGENT = "EyeOfProvidence/1.0 (News Aggregator)"
