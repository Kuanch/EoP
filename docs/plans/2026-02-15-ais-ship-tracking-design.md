# AIS Ship Tracking on Map — Design

## Overview
Add real-time ship tracking to the map tab via AISstream.io WebSocket API. Ships appear as a separate layer from aircraft, with vessel-type coloring and independent toggle controls.

## Architecture
```
AISstream.io (WSS) → collectors/ships.py → ws_manager → map.js (shipsLayer)
```

## Backend: collectors/ships.py
- Persistent WebSocket to `wss://stream.aisstream.io/v0/stream`
- Subscribe to Taiwan Strait bbox `[[21.0, 116.0], [27.0, 123.0]]`
- Filter `PositionReport` messages only
- `ships_cache` dict keyed by MMSI, expire entries after 30 min no update
- Batch broadcast `{module: "ships", data: [...]}` every 30 seconds
- Fields: mmsi, name, lat, lon, sog, cog, heading, vessel_type, last_seen

## Frontend: map.js
- New `shipsLayer` LayerGroup, separate from `militaryLayer`
- Boat-shaped SVG icons rotated by heading
- Color by vessel type: cargo=blue, tanker=red, fishing=green, military=gray, passenger=purple, other=orange
- Tooltip: name, MMSI, type, speed, heading
- Layer toggle buttons: [Aircraft] [Ships]

## Config
- `AISSTREAM_API_KEY` env var
- `SHIPS_BROADCAST_INTERVAL = 30`
- Taiwan Strait bbox reused from MONITORED_REGIONS

## API
- `GET /api/ships` — returns current cache
