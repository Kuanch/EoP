"""AIS ship tracker — Taiwan MPB (polling) + AISstream.io (WebSocket)."""

import asyncio
import json
import logging
import time

import httpx
import websockets

from config import (
    AISSTREAM_API_KEY, AISSTREAM_WS_URL,
    SHIP_REGIONS, SHIPS_BROADCAST_INTERVAL, HTTP_TIMEOUT,
)
from ws_manager import manager

logger = logging.getLogger(__name__)

ships_cache: dict[str, dict] = {}  # keyed by MMSI

SHIP_EXPIRE_SECONDS = 1800  # 30 min

# MMSI MID (first 3 digits) → country name
MID_COUNTRY = {
    "201": "Albania", "202": "Andorra", "203": "Austria", "204": "Azores",
    "205": "Belgium", "206": "Belarus", "207": "Bulgaria", "208": "Vatican",
    "209": "Cyprus", "210": "Cyprus", "211": "Germany", "212": "Cyprus",
    "213": "Georgia", "214": "Moldova", "215": "Malta", "216": "Armenia",
    "218": "Germany", "219": "Denmark", "220": "Denmark", "224": "Spain",
    "225": "Spain", "226": "France", "227": "France", "228": "France",
    "229": "Malta", "230": "Finland", "231": "Faroe Islands",
    "232": "United Kingdom", "233": "United Kingdom", "234": "United Kingdom",
    "235": "United Kingdom", "236": "Gibraltar", "237": "Greece",
    "238": "Croatia", "239": "Greece", "240": "Greece", "241": "Greece",
    "242": "Morocco", "243": "Hungary", "244": "Netherlands",
    "245": "Netherlands", "246": "Netherlands", "247": "Italy",
    "248": "Malta", "249": "Malta", "250": "Ireland", "251": "Iceland",
    "252": "Liechtenstein", "253": "Luxembourg", "254": "Madeira",
    "255": "Portugal", "256": "Malta", "257": "Norway", "258": "Norway",
    "259": "Norway", "261": "Poland", "263": "Portugal", "264": "Romania",
    "265": "Sweden", "266": "Sweden", "267": "Slovak Republic",
    "268": "San Marino", "269": "Switzerland", "270": "Czech Republic",
    "271": "Turkey", "272": "Ukraine", "273": "Russia", "274": "North Macedonia",
    "275": "Latvia", "276": "Estonia", "277": "Lithuania", "278": "Slovenia",
    "279": "Serbia",
    "301": "Anguilla", "303": "Alaska", "304": "Antigua and Barbuda",
    "305": "Antigua and Barbuda", "306": "Curacao", "307": "Aruba",
    "308": "Bahamas", "309": "Bahamas", "310": "Bermuda",
    "311": "Bahamas", "312": "Belize", "314": "Barbados",
    "316": "Canada", "319": "Cayman Islands", "321": "Costa Rica",
    "323": "Cuba", "325": "Dominica", "327": "Dominican Republic",
    "329": "Guadeloupe", "330": "Grenada", "331": "Greenland",
    "332": "Guatemala", "334": "Honduras", "336": "Haiti",
    "338": "United States", "339": "Jamaica", "341": "Saint Kitts and Nevis",
    "343": "Saint Lucia", "345": "Mexico", "347": "Martinique",
    "348": "Montserrat", "350": "Nicaragua", "351": "Panama",
    "352": "Panama", "353": "Panama", "354": "Panama",
    "355": "Panama", "356": "Panama", "357": "Panama",
    "358": "Puerto Rico", "359": "El Salvador", "361": "Saint Pierre and Miquelon",
    "362": "Trinidad and Tobago", "364": "Turks and Caicos",
    "366": "United States", "367": "United States", "368": "United States",
    "369": "United States", "370": "Panama", "371": "Panama",
    "372": "Panama", "373": "Panama", "374": "Panama", "375": "Saint Vincent",
    "376": "Saint Vincent", "377": "Saint Vincent", "378": "British Virgin Islands",
    "379": "US Virgin Islands",
    "401": "Afghanistan", "403": "Saudi Arabia", "405": "Bangladesh",
    "408": "Bahrain", "410": "Bhutan", "412": "China", "413": "China",
    "414": "China", "416": "Taiwan", "417": "Sri Lanka",
    "419": "India", "422": "Iran", "423": "Azerbaijan",
    "425": "Iraq", "428": "Israel", "431": "Japan",
    "432": "Japan", "434": "Turkmenistan", "436": "Kazakhstan",
    "437": "Uzbekistan", "438": "Jordan", "440": "South Korea",
    "441": "South Korea", "443": "Palestine", "445": "North Korea",
    "447": "Kuwait", "450": "Lebanon", "451": "Kyrgyzstan",
    "453": "Macau", "455": "Maldives", "457": "Mongolia",
    "459": "Nepal", "461": "Oman", "463": "Pakistan",
    "466": "Qatar", "468": "Syria", "470": "UAE",
    "471": "UAE", "472": "Tajikistan", "473": "Yemen",
    "475": "Yemen", "477": "Hong Kong",
    "501": "Antarctica", "503": "Australia", "506": "Myanmar",
    "508": "Brunei", "510": "Micronesia", "511": "Palau",
    "512": "New Zealand", "514": "Cambodia", "515": "Cambodia",
    "516": "Christmas Island", "518": "Cook Islands",
    "520": "Fiji", "523": "Cocos Islands", "525": "Indonesia",
    "529": "Kiribati", "531": "Laos", "533": "Malaysia",
    "536": "Northern Mariana Islands", "538": "Marshall Islands",
    "540": "New Caledonia", "542": "Niue", "544": "Nauru",
    "546": "French Polynesia", "548": "Philippines",
    "553": "Papua New Guinea", "555": "Pitcairn Island",
    "557": "Solomon Islands", "559": "American Samoa",
    "561": "Samoa", "563": "Singapore", "564": "Singapore",
    "565": "Singapore", "566": "Singapore", "567": "Thailand",
    "570": "Tonga", "572": "Tuvalu", "574": "Vietnam",
    "576": "Vanuatu", "577": "Vanuatu", "578": "Wallis and Futuna",
    "601": "South Africa", "603": "Angola", "605": "Algeria",
    "607": "Saint Paul", "608": "Ascension Island",
    "609": "Burundi", "610": "Benin", "611": "Botswana",
    "612": "Central African Republic", "613": "Cameroon",
    "615": "Congo", "616": "Comoros", "617": "Cape Verde",
    "618": "Antarctica", "619": "Ivory Coast",
    "620": "Comoros", "621": "Djibouti", "622": "Egypt",
    "624": "Ethiopia", "625": "Eritrea", "626": "Gabon",
    "627": "Ghana", "629": "Gambia", "630": "Guinea-Bissau",
    "631": "Equatorial Guinea", "632": "Guinea", "633": "Burkina Faso",
    "634": "Kenya", "635": "Antarctica", "636": "Liberia",
    "637": "Liberia", "638": "South Sudan", "642": "Libya",
    "644": "Lesotho", "645": "Mauritius", "647": "Madagascar",
    "649": "Mali", "650": "Mozambique", "654": "Mauritania",
    "655": "Malawi", "656": "Niger", "657": "Nigeria",
    "659": "Namibia", "660": "Reunion", "661": "Rwanda",
    "662": "Sudan", "663": "Senegal", "664": "Seychelles",
    "665": "Saint Helena", "666": "Somalia", "667": "Sierra Leone",
    "668": "Sao Tome and Principe", "669": "Eswatini",
    "670": "Chad", "671": "Togo", "672": "Tunisia",
    "674": "Tanzania", "675": "Uganda", "676": "DR Congo",
    "677": "Tanzania", "678": "Zambia", "679": "Zimbabwe",
    "701": "Argentina", "710": "Brazil", "720": "Bolivia",
    "725": "Chile", "730": "Colombia", "735": "Ecuador",
    "740": "Falkland Islands", "745": "Guiana", "750": "Guyana",
    "755": "Paraguay", "760": "Peru", "765": "Suriname",
    "770": "Uruguay", "775": "Venezuela",
    "108": "Taiwan",  # some Taiwan vessels use 108 prefix
    "123": "Taiwan",  # some Taiwan fishing vessels
    "994": "Taiwan",  # EPIRB/PLB registrations
}


def _get_country(mmsi: str) -> str:
    """Get country name from MMSI MID prefix."""
    if len(mmsi) >= 3:
        return MID_COUNTRY.get(mmsi[:3], "Unknown")
    return "Unknown"

# Taiwan MPB AIS endpoint (free, no key needed)
TAIWAN_AIS_URL = "https://mpbais.motcmpb.gov.tw/aismpb/tools/geojsonais.ashx"
TAIWAN_AIS_POLL_INTERVAL = 60  # seconds

VESSEL_TYPE_NAMES = {
    30: "Fishing",
    31: "Tug", 32: "Tug",
    33: "Dredger", 34: "Diving",
    35: "Military",
    36: "Sailing", 37: "Yacht",
    40: "High-speed",
    50: "Pilot", 51: "SAR", 52: "Tug", 53: "Port Tender", 55: "Law Enforcement",
}


def _vessel_type_name(code: int) -> str:
    if code in VESSEL_TYPE_NAMES:
        return VESSEL_TYPE_NAMES[code]
    if 60 <= code <= 69:
        return "Passenger"
    if 70 <= code <= 79:
        return "Cargo"
    if 80 <= code <= 89:
        return "Tanker"
    return "Other"


def _build_bounding_boxes() -> list:
    boxes = []
    for coords in SHIP_REGIONS.values():
        boxes.append(coords)
    return boxes


def _expire_stale_ships():
    now = time.time()
    expired = [mmsi for mmsi, ship in ships_cache.items()
               if now - ship["_last_update"] > SHIP_EXPIRE_SECONDS]
    for mmsi in expired:
        del ships_cache[mmsi]
    if expired:
        logger.debug(f"[ships] Expired {len(expired)} stale ships")


def get_ships_list(filter_mode: str = "china", country: str = "") -> list[dict]:
    """Return cache as list without internal fields.

    filter_mode:
      "china"    — China-flagged ships only (default)
      "known"    — moving + known vessel type only
      "moving"   — all moving ships
      "notable"  — skip stationary unknowns
      "all"      — everything
    country:
      optional country name filter (case-insensitive partial match)
    """
    _expire_stale_ships()
    result = []
    country_lower = country.lower().strip() if country else ""
    for ship in ships_cache.values():
        if ship.get("lat") is None or ship.get("lon") is None:
            continue

        mmsi = ship.get("mmsi", "")
        ship_country = _get_country(mmsi)

        # Country filter
        if country_lower and country_lower not in ship_country.lower():
            continue

        sog = ship.get("sog") or 0
        vtype = ship.get("vessel_type", 0)
        is_unknown = (vtype == 0 or _vessel_type_name(vtype) == "Other")

        if filter_mode == "china":
            if ship_country != "China":
                continue
        elif filter_mode == "known":
            if is_unknown or sog < 0.5:
                continue
        elif filter_mode == "moving":
            if sog < 0.5:
                continue
        elif filter_mode == "notable":
            if is_unknown and sog < 0.5:
                continue

        s = {k: v for k, v in ship.items() if not k.startswith("_")}
        s["country"] = ship_country
        result.append(s)
    return result


class ShipCollector:
    """Dual-source AIS collector: Taiwan MPB + AISstream.io."""

    def __init__(self):
        self.name = "ships"
        self._running = False

    async def run(self):
        self._running = True
        logger.info("[ships] Collector started")

        # Always start broadcast loop
        asyncio.create_task(self._broadcast_loop())

        # Always start Taiwan MPB polling (free, no key)
        asyncio.create_task(self._poll_taiwan_ais())

        # Start AISstream if API key is set
        if AISSTREAM_API_KEY:
            asyncio.create_task(self._aisstream_loop())
        else:
            logger.info("[ships] No AISSTREAM_API_KEY, using Taiwan MPB only")

        # Keep alive
        while self._running:
            await asyncio.sleep(60)

    # --- Taiwan MPB AIS (polling) ---

    async def _poll_taiwan_ais(self):
        """Poll Taiwan Maritime and Port Bureau AIS GeoJSON endpoint."""
        logger.info("[ships] Taiwan MPB AIS polling started")
        while self._running:
            try:
                async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
                    resp = await client.get(TAIWAN_AIS_URL, headers={
                        "Referer": "https://mpbais.motcmpb.gov.tw/aismpb/",
                        "User-Agent": "Mozilla/5.0",
                    })
                    if resp.status_code == 200:
                        data = resp.json()
                        features = data.get("features", [])
                        count = 0
                        for f in features:
                            props = f.get("properties", {})
                            mmsi = str(props.get("MMSI", ""))
                            if not mmsi:
                                continue
                            lat = props.get("Latitude")
                            lon = props.get("Longitude")
                            if lat is None or lon is None:
                                continue

                            vessel_type = props.get("Ship_and_Cargo_Type", 0) or 0
                            sog = props.get("SOG")
                            cog = props.get("COG")
                            ship_name = (props.get("ShipName") or "").strip()

                            ships_cache[mmsi] = {
                                "mmsi": mmsi,
                                "name": ship_name if ship_name else "Unknown",
                                "lat": round(lat, 5),
                                "lon": round(lon, 5),
                                "sog": round(sog, 1) if sog is not None else None,
                                "cog": round(cog, 1) if cog is not None else None,
                                "heading": round(cog, 0) if cog is not None else None,
                                "vessel_type": vessel_type,
                                "vessel_type_name": _vessel_type_name(vessel_type),
                                "nav_status": props.get("Navigational_Status"),
                                "source": "TW-MPB",
                                "_last_update": time.time(),
                            }
                            count += 1
                        logger.info(f"[ships] Taiwan MPB: {count} ships loaded")
                    else:
                        logger.warning(f"[ships] Taiwan MPB HTTP {resp.status_code}")
            except Exception as e:
                logger.error(f"[ships] Taiwan MPB error: {e}")
            await asyncio.sleep(TAIWAN_AIS_POLL_INTERVAL)

    # --- AISstream.io (WebSocket) ---

    async def _aisstream_loop(self):
        """Persistent WebSocket connection to AISstream.io."""
        logger.info(f"[ships] AISstream started, {len(SHIP_REGIONS)} region(s)")
        while self._running:
            try:
                await self._connect_aisstream()
            except Exception as e:
                logger.error(f"[ships] AISstream error: {e}")
            if self._running:
                await asyncio.sleep(10)

    async def _connect_aisstream(self):
        bboxes = _build_bounding_boxes()
        subscription = {
            "APIKey": AISSTREAM_API_KEY,
            "BoundingBoxes": bboxes,
            "FilterMessageTypes": ["PositionReport", "ShipStaticData"],
        }

        async with websockets.connect(AISSTREAM_WS_URL, ping_interval=30, ping_timeout=10) as ws:
            await ws.send(json.dumps(subscription))
            logger.info(f"[ships] AISstream connected, {len(bboxes)} bbox(es)")

            async for raw in ws:
                if not self._running:
                    break
                try:
                    msg = json.loads(raw)
                    self._process_aisstream_msg(msg)
                except json.JSONDecodeError:
                    continue
                except Exception as e:
                    logger.debug(f"[ships] AISstream msg error: {e}")

    def _process_aisstream_msg(self, msg: dict):
        msg_type = msg.get("MessageType")
        meta = msg.get("MetaData", {})
        mmsi = str(meta.get("MMSI", ""))
        if not mmsi:
            return

        if msg_type == "ShipStaticData":
            static = msg.get("Message", {}).get("ShipStaticData", {})
            if not static:
                return
            vessel_type = static.get("Type", 0) or 0
            ship_name = (static.get("Name") or meta.get("ShipName") or "").strip()
            if mmsi in ships_cache:
                ships_cache[mmsi]["vessel_type"] = vessel_type
                ships_cache[mmsi]["vessel_type_name"] = _vessel_type_name(vessel_type)
                if ship_name:
                    ships_cache[mmsi]["name"] = ship_name
            return

        if msg_type != "PositionReport":
            return

        report = msg.get("Message", {}).get("PositionReport", {})
        if not report:
            return

        lat = meta.get("latitude") or report.get("Latitude")
        lon = meta.get("longitude") or report.get("Longitude")
        if lat is None or lon is None:
            return

        ship_name = (meta.get("ShipName") or "").strip()
        sog = report.get("Sog")
        cog = report.get("Cog")
        heading = report.get("TrueHeading")
        if heading == 511:
            heading = cog

        existing = ships_cache.get(mmsi, {})
        vessel_type = existing.get("vessel_type", 0)
        vessel_type_name = existing.get("vessel_type_name", "Other")

        ships_cache[mmsi] = {
            "mmsi": mmsi,
            "name": ship_name if ship_name else existing.get("name", "Unknown"),
            "lat": round(lat, 5),
            "lon": round(lon, 5),
            "sog": round(sog, 1) if sog is not None else None,
            "cog": round(cog, 1) if cog is not None else None,
            "heading": round(heading, 0) if heading is not None else None,
            "vessel_type": vessel_type,
            "vessel_type_name": vessel_type_name,
            "nav_status": report.get("NavigationalStatus"),
            "source": "AISstream",
            "_last_update": time.time(),
        }

    # --- Broadcast ---

    async def _broadcast_loop(self):
        while self._running:
            await asyncio.sleep(SHIPS_BROADCAST_INTERVAL)
            ships = get_ships_list()
            if ships:
                await manager.broadcast("ships", ships)
                logger.info(f"[ships] Broadcast {len(ships)} ships")

    def stop(self):
        self._running = False
