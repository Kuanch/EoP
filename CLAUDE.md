# EoP — Edge of Panic

Real-time geopolitical threat monitoring dashboard. Aggregates news, markets, military aircraft, cyber threats, ship tracking, prediction markets, and Pentagon activity into a single FastAPI + WebSocket interface.

## Deployment

The production server runs on **192.168.0.148** (sixigma-XPS-13, Ubuntu Linux), co-located with the ELK stack.

| Service | Container | Port | Notes |
|---------|-----------|------|-------|
| EoP FastAPI | `fastapi-login-app` | 8000 | Main dashboard |
| Cloudflare tunnel | `cloudflared-tunnel` | — | Routes kuanchlee.com -> app |
| ntfy | `eop-ntfy` | 8090 | Push notifications |
| Elasticsearch 8.17 | `elasticsearch` | 9200 | Honeypot + future analytics |
| Kibana 8.17 | `kibana` | 5601 | Analyst workbench |
| Logstash | `logstash` | 5000, 5044 | Log pipeline |

Public URL: `https://kuanchlee.com` (via Cloudflare Tunnel, free TLS + DDoS protection)

### Deploy / Rebuild

```bash
cd ~/EoP && docker compose up -d --build
```

### Cloudflare Tunnel

Uses **Method 2** (named tunnel with credential files), NOT token-based. Credentials at `~/.cloudflared/`:
- Tunnel UUID: `ccaf629b-f4f1-47f6-bd3b-3e9ee600ba73`
- Docker config: `~/.cloudflared/config-docker.yml` (uses `http://fastapi-login-app:8000`)
- Host config: `~/.cloudflared/config.yml` (uses `http://localhost:8000`)

## Honeypot Infrastructure

A Cowrie SSH/Telnet honeypot runs on a GCP VM in Taiwan (asia-east1), shipping attack logs to the co-located Elasticsearch via Tailscale mesh VPN.

| Component | Location | IP |
|-----------|----------|-----|
| Cowrie probe | GCP asia-east1-b | Tailscale: 100.108.213.106 |
| ELK stack | 192.168.0.148 | Tailscale: 100.101.38.12 |

ES index: `.ds-cowrie-*` | Data view: "Cowrie Honeypot" | Dashboard: `cowrie-dashboard-v3`

The `HoneypotCollector` (queries ES for attack metrics) and 3-tier composite criterion are **planned but not yet implemented**. See `docs/plans/2026-04-05-elk-honeypot-infrastructure.md` for the full integration plan.

## Development

- Python 3.12 + FastAPI + vanilla JS (no frontend framework)
- SQLite for user auth and persistence (`data/users.db`)
- All collectors inherit `BaseCollector` except `ShipCollector`
- WebSocket broadcasts real-time data per module
- Threat engine: keyword rules + Claude Haiku LLM two-pass pipeline
- API keys loaded from `.env` (all optional, graceful degradation)

## Key Conventions

- All API endpoints require session auth except `/login`
- Use `source.ip` (ECS field) not `src_ip` (raw Cowrie field) in ES queries
- Cloudflare tunnel hostname must be `KUANCHLEE.COM` (case-sensitive in config)
- Cookie `samesite="lax"` required behind Cloudflare proxy (not `strict`)
- Static assets (`/static/js/`, `/static/css/`) are auth-protected
