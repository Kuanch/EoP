# ELK + Honeypot Probe Infrastructure

**Date:** 2026-04-05
**Status:** Deployed — infrastructure live, EoP integration pending
**Reviewed by:** Codex (GPT-5.4), Gemini (3.1 Pro) — 21 findings addressed below

## Summary

We deployed a Cowrie SSH/Telnet honeypot on a GCP VM in Taiwan (asia-east1), connected it to an existing ELK stack via Tailscale mesh VPN, and created a Kibana dashboard for attack visualization. This is the foundation for a future composite threat criterion in EoP that correlates honeypot attack pressure with MERIT Network Telescope signals.

**Current vs future state:** The infrastructure (Cowrie → Filebeat → ES → Kibana) is deployed and running. EoP does **not** yet query ES — the `HoneypotCollector` and composite criterion are planned but not implemented.

## Motivation

The current EoP cyber module monitors internet outages via IODA API (MERIT-NT and BGP signals for Taiwan, Ukraine, Iran), fetches cyber news from RSS feeds, and tracks CISA KEV vulnerabilities. It detects *macro-level* disruptions but lacks:

1. **First-party attack telemetry** — we rely entirely on third-party data (IODA, RSS). A personal honeypot gives us real-time attack pressure data we control.
2. **Cross-domain correlation** — honeypot attack surges + MERIT degradation + military activity + market panic = much stronger signal than any single source.
3. **Historical analysis** — `signal_history.json` is limited. ELK provides full-text search, aggregations, and retention beyond the 7-day signal baseline window.

## Architecture

```
Internet Attackers
       │
       ▼
┌──────────────────────────────────┐
│  GCP VM: cowrie-probe            │
│  asia-east1-b (Taiwan)           │
│  e2-micro (0.25 vCPU, 1GB RAM)  │
│                                  │
│  Port 22  → Cowrie SSH honeypot  │  ← open to internet (0.0.0.0/0)
│  Port 23  → Cowrie Telnet        │  ← open to internet (0.0.0.0/0)
│  Port 2222 → Real SSH (admin)    │  ← Tailscale only (100.64.0.0/10)
│                                  │
│  Docker: cowrie/cowrie@sha256:... │
│  Limits: 384MB mem, 0.2 CPU     │
│  Logs: /opt/cowrie/log/cowrie.json│
│  Downloads: /opt/cowrie/data/    │
│                                  │
│  Filebeat 8.19.13                │
│  Reads cowrie.json               │
│  Ships to ES via Tailscale       │
└──────────┬───────────────────────┘
           │ Tailscale mesh (WireGuard encrypted)
           │ cowrie-probe (100.108.213.106)
           │        ↕
           │ elk-xps (100.101.38.12)
           ▼
┌──────────────────────────────────┐
│  ELK Machine: sixigma-XPS-13    │
│  192.168.0.148 (WLAN)           │
│                                  │
│  Elasticsearch 8.17.0 (:9200)   │
│  Kibana 8.17.0 (:5601)          │
│  Logstash (:5000, :5044)        │
│                                  │
│  Index: .ds-cowrie-*             │
│  Data view: "Cowrie Honeypot"    │
│  Dashboard: cowrie-dashboard-v3  │
└──────────┬───────────────────────┘
           │ WLAN (192.168.0.x)
           ▼
┌──────────────────────────────────┐
│  WSL: EoP Dashboard             │
│                                  │
│  FastAPI + WebSocket             │
│  (future: HoneypotCollector      │
│   will query ES for metrics)     │
└──────────────────────────────────┘
```

## Component Details

### 1. GCP VM (cowrie-probe)

| Property | Value |
|----------|-------|
| Project | `eop-tpot` |
| Zone | `asia-east1-b` |
| Machine type | `e2-micro` (0.25 vCPU, 1GB RAM + 256MB swap) |
| OS | Debian 12 |
| Public IP | `34.80.234.119` |
| Tailscale IP | `100.108.213.106` |
| Monthly cost | **~$7** (billable — free tier only applies to `us-*` regions) |
| Service account | `tpot-839@eop-tpot.iam.gserviceaccount.com` |

**Why Taiwan (asia-east1)?** A probe *in* Taiwan receiving increased attack traffic is a much stronger "Taiwan under cyber attack" signal than a probe elsewhere. The geographic placement is the whole point — it puts our canary inside the blast radius.

**Why e2-micro?** Cheapest option that fits the $10/month budget. Cowrie is lightweight (Python/Twisted). Observed usage: ~860MB RAM at idle with Cowrie + Filebeat + OS. Docker resource limits (384MB for Cowrie) and 256MB swap prevent OOM kills under attack floods.

#### Firewall Rules

Two separate GCP firewall rules, split by purpose:

| Rule | Ports | Source | Purpose |
|------|-------|--------|---------|
| `allow-honeypot-ports` | tcp:22, tcp:23 | `0.0.0.0/0` | Honeypot — must be open to attract attackers |
| `allow-admin-ssh` | tcp:2222 | `100.64.0.0/10` | Admin SSH — restricted to Tailscale CGNAT range only |

**Port 2222 is NOT accessible from the public internet.** Admin access requires Tailscale mesh connectivity.

#### Service Account & Credentials

The SA key (`eop-tpot-7ffc8178d524.json`) is gitignored and stored only on the WSL dev machine. It is used only for `gcloud compute` management operations (create/delete VMs, firewall rules), not at runtime.

**SA roles** (broader than strictly needed — these were assigned during initial setup):
- `compute.instanceAdmin.v1` — create/manage VMs
- `compute.securityAdmin` — create/manage firewall rules
- `iam.serviceAccountUser` — attach SA to VM at creation time

These roles are only exercised during infrastructure provisioning, not by the running VM. The SA key should be rotated if compromised. Consider migrating to Workload Identity Federation in the future to eliminate long-lived keys.

#### SSH Access

Admin SSH requires Tailscale. From a machine on the tailnet:
```bash
ssh -p 2222 -i ~/.ssh/google_compute_engine sixigma@100.108.213.106
```

Or via jump host through the ELK machine:
```bash
ssh -J sixigma@192.168.0.148 -p 2222 -i ~/.ssh/google_compute_engine sixigma@100.108.213.106
```

### 2. Cowrie Honeypot

Cowrie is a medium-interaction SSH/Telnet honeypot. It emulates a real Linux system and logs:

- **Session events:** connect, disconnect, duration
- **Authentication:** usernames, passwords, SSH keys attempted
- **Commands:** what attackers type after "successful" login
- **File downloads:** malware dropped by attackers (stored in `/opt/cowrie/data/`, auto-cleaned after 3 days)
- **Client fingerprints:** SSH version strings, HASSH fingerprints, key exchange algorithms

**Login behavior:** Cowrie uses a default credential set (typically `root:*` with various common passwords). When Cowrie "accepts" a login (`cowrie.login.success`), the attacker enters a fake shell environment — they can type commands but are interacting with an emulated filesystem. This is by design: it captures post-exploitation behavior. A `login.success` event does NOT mean the real system was compromised.

**Container setup (production command):**
```bash
sudo docker run -d \
  --name cowrie \
  --restart=always \
  --memory=384m \
  --memory-swap=512m \
  --cpus=0.2 \
  --pids-limit=100 \
  -p 22:2222 \
  -p 23:2223 \
  -v /opt/cowrie/log:/cowrie/cowrie-git/var/log/cowrie \
  -v /opt/cowrie/data:/cowrie/cowrie-git/var/lib/cowrie/downloads \
  cowrie/cowrie@sha256:a2e74d2fbd53f86098d8c366e14ad6656c92c8c1ab36de68ca46e26fe9ab294e
```

**Resource limits:**
- Memory: 384MB hard limit, 512MB with swap — prevents Cowrie from OOM-killing Filebeat or Tailscale
- CPU: 0.2 (20% of one core) — sufficient for honeypot interaction, prevents CPU exhaustion under flood
- PIDs: 100 max — prevents fork bombs from spawned emulated processes

**Image pinning:** The container uses a specific `sha256` digest, not `:latest`. To upgrade, pull a new version, verify it locally, update the digest, and recreate the container.

**Port mapping rationale:** Real SSH was moved to port 2222 (`/etc/ssh/sshd_config` → `Port 2222`) so Cowrie can occupy port 22, which is what scanners and botnets target.

**Log format:** JSON (one event per line in `/opt/cowrie/log/cowrie.json`). Example:
```json
{
  "eventid": "cowrie.session.connect",
  "src_ip": "203.0.113.42",
  "src_port": 54321,
  "dst_ip": "172.17.0.2",
  "dst_port": 2222,
  "session": "e688e374a113",
  "protocol": "ssh",
  "timestamp": "2026-04-04T17:03:04.262759Z"
}
```

**Note on `dst_ip`:** The `172.17.0.2` is the Docker container-internal IP, NOT the public probe address. The public IP (`34.80.234.119`) does not appear in Cowrie logs. When building dashboards or correlation logic, use `src_ip` (attacker) for analysis. The `dst_ip` field is not useful for geolocation.

**Log volume permissions:** The mounted volume must be owned by uid 1000 (Cowrie's non-root user):
```bash
sudo chown -R 1000:1000 /opt/cowrie/log /opt/cowrie/data
```

**Malware downloads:** Attacker-dropped files are stored in `/opt/cowrie/data/`, which is a bind mount to the host filesystem. They are NOT sandboxed — the files exist on the VM's disk. However, Cowrie writes them as its non-root user (uid 1000), and a daily cron job (`/etc/cron.daily/cowrie-cleanup`) deletes files older than 3 days. Files are NOT scanned or forwarded — they are retained only for short-term forensic inspection if needed. Do not execute any files from this directory.

### 3. Filebeat Configuration

Filebeat runs as a systemd service on the GCP VM, reading Cowrie's JSON log and shipping to Elasticsearch over the Tailscale network.

**Config file:** `/etc/filebeat/filebeat.yml`

```yaml
filebeat.inputs:
  - type: log
    enabled: true
    paths:
      - /opt/cowrie/log/cowrie.json
    json.keys_under_root: true
    json.add_error_key: true
    fields:
      source: cowrie-honeypot
      location: gcp-asia-east1
      sensor: eop-tw-probe
    fields_under_root: false

output.elasticsearch:
  hosts: ["http://100.101.38.12:9200"]
  username: "elastic"
  password: "<see credentials section>"
  index: "cowrie-%{+yyyy.MM.dd}"

setup.ilm.enabled: false
setup.template.name: "cowrie"
setup.template.pattern: "cowrie-*"
setup.template.settings:
  index.number_of_shards: 1
  index.number_of_replicas: 0

processors:
  - timestamp:
      field: timestamp
      layouts:
        - "2006-01-02T15:04:05.999999Z"
  - rename:
      fields:
        - from: "src_ip"
          to: "source.ip"
        - from: "dst_ip"
          to: "destination.ip"
        - from: "src_port"
          to: "source.port"
        - from: "dst_port"
          to: "destination.port"
      ignore_missing: true
```

**Key decisions:**
- `json.keys_under_root: true` — Cowrie fields (eventid, src_ip, etc.) are promoted to top-level, not nested under `json.*`.
- `fields_under_root: false` — our custom fields (source, location, sensor) stay under `fields.*` to avoid collision with the ECS `source.*` namespace created by the rename processor.
- Processors rename Cowrie's `src_ip`/`dst_ip` to ECS-compatible `source.ip`/`destination.ip`. This does NOT collide with `fields.source` because `fields_under_root: false` keeps them separate.

**Data stream note:** Despite configuring `index: "cowrie-%{+yyyy.MM.dd}"` and `setup.ilm.enabled: false`, Elasticsearch created a data stream (`.ds-cowrie-*`) rather than daily indices. This is because the Filebeat 8.x template includes a composable index template that matches `cowrie-*` and creates a data stream. The Kibana data view uses `.ds-cowrie-*` to match.

**Transport security:** Filebeat uses HTTP (not HTTPS) over Tailscale. This is acceptable because Tailscale uses WireGuard encryption at the network layer — all traffic between nodes is encrypted. The credentials are still exposed in the Filebeat config file on the VM.

**Note:** Filebeat ships to Elasticsearch directly (not Logstash) to save RAM on the constrained e2-micro VM.

### 4. Log Rotation & Disk Management

**On the GCP VM (10GB disk):**

Log rotation config at `/etc/logrotate.d/cowrie`:
```
/opt/cowrie/log/cowrie.json {
    daily
    rotate 7
    size 50M
    compress
    delaycompress
    missingok
    notifempty
    copytruncate
}
```

This keeps ~7 days of logs on the VM, compressed. `copytruncate` avoids restarting Cowrie or Filebeat.

**On the ELK machine (ES retention):**

ES index retention is currently **not enforced automatically**. ILM is disabled. Because Cowrie data uses a data stream (`.ds-cowrie-*`), standard index deletion does not work — you must use the data stream API:
```bash
# List data streams
curl -s -u elastic:<password> "http://localhost:9200/_data_stream/cowrie-*"

# Delete an entire data stream (all backing indices)
curl -X DELETE -u elastic:<password> "http://localhost:9200/_data_stream/cowrie-2026.03.15"
```
The recommended approach is to re-enable ILM with a hot-delete policy rather than manual cleanup.

**TODO:** Set up an ILM policy with 30-day retention on the ELK machine. The 7-day on-VM rotation is about probe disk space; ES retention should be longer (30+ days) to support the 7-day median baseline calculation for the future composite criterion.

### 5. Tailscale Mesh VPN

Tailscale connects the GCP VM to the home ELK machine over an encrypted WireGuard tunnel, without exposing any ports to the public internet.

| Host | Tailscale IP | Hostname | Role |
|------|-------------|----------|------|
| GCP VM | `100.108.213.106` | `cowrie-probe` | Honeypot + Filebeat |
| ELK XPS | `100.101.38.12` | `elk-xps` | ES + Kibana + Logstash |

**Why Tailscale instead of port forwarding?**
- No need to expose Elasticsearch (port 9200) or Logstash (port 5044) to the public internet
- No router configuration needed
- Encrypted by default (WireGuard)
- Survives IP changes (both home ISP and GCP)
- Free for personal use (up to 100 devices)

**Tailscale account:** Personal account. Recovery depends on the account's auth provider (Google/Microsoft/etc). If access is lost, the probe can still be reached via `gcloud compute serial-console` or by temporarily re-opening port 2222 in GCP firewall.

**Tailscale ACLs (recommended):** The honeypot is an internet-facing attack target. If Cowrie or Docker is compromised, the attacker could pivot to the ELK machine via Tailscale. To mitigate this, configure Tailscale ACLs in the admin console (https://login.tailscale.com/admin/acls) to restrict `cowrie-probe` to only ES port 9200 on `elk-xps`:

```json
{
  "acls": [
    {"action": "accept", "src": ["cowrie-probe"], "dst": ["elk-xps:9200"]},
    {"action": "accept", "src": ["elk-xps"], "dst": ["cowrie-probe:2222"]},
    {"action": "accept", "src": ["eop-wsl"], "dst": ["*:*"]}
  ]
}
```

This ensures a compromised honeypot can only reach Elasticsearch ingestion, not Kibana or other services.

**Installation:**
```bash
curl -fsSL https://tailscale.com/install.sh | sudo sh
sudo tailscale up --hostname=<hostname>
# Approve the auth URL in the browser
```

### 6. ELK Stack

The ELK stack runs on a Dell XPS 13 (sixigma-XPS-13-9360) on the home WLAN, all via Docker containers.

| Service | Container | WLAN Endpoint | Tailscale Endpoint |
|---------|-----------|---------------|-------------------|
| Elasticsearch 8.17.0 | `elasticsearch` | `192.168.0.148:9200` | `100.101.38.12:9200` |
| Kibana 8.17.0 | `kibana` | `192.168.0.148:5601` | `100.101.38.12:5601` |
| Logstash | `logstash` | `192.168.0.148:5000`, `:5044` | `100.101.38.12:5000`, `:5044` |
| ntfy (EoP notifier) | `eop-ntfy` | `192.168.0.148:8090` | — |

**Credentials:** Stored separately — not documented here. The default `elastic` superuser is currently used for both Filebeat ingestion and Kibana access. **TODO:** Create a dedicated `cowrie_writer` role with index-write-only permissions for Filebeat, and a `cowrie_reader` role for EoP dashboard queries.

**Canonical IP:** Use `192.168.0.148` for all WLAN access. The `.147` IP was observed responding to ES queries during initial setup but its origin is unverified — it may be a secondary interface or Docker bridge artifact. Do not rely on it.

### 7. Kibana Dashboard

**Dashboard name:** "EoP Cowrie Honeypot - Taiwan Probe"
**Dashboard ID:** `cowrie-dashboard-v3`
**URL:** `http://192.168.0.148:5601/app/dashboards#/view/cowrie-dashboard-v3`

**Data view:** "Cowrie Honeypot" (ID: `8c16355f-a75f-45de-8cea-d7ed887fbe29`)
**Index pattern:** `.ds-cowrie-*`

**Panels (10 total):**

| Panel | Type | Data Source |
|-------|------|-------------|
| Total Events | Metric (count) | All events |
| Unique Attacker IPs | Metric (cardinality) | `source.ip` |
| Total Sessions | Metric (cardinality) | `session` |
| Attack Timeline | Histogram (date histogram) | `@timestamp` |
| Top Attacker IPs | Horizontal bar (terms) | `source.ip` |
| Event Types | Donut (terms) | `eventid` |
| Top Usernames | Horizontal bar (terms) | `username` |
| Top Passwords | Horizontal bar (terms) | `password` |
| SSH Client Versions | Donut (terms) | `version` (filtered: `eventid:cowrie.client.version`) |
| Cowrie Events | Saved search table | `eventid`, `source.ip`, `username`, `password`, `message` |

**Settings:**
- Default time range: last 24 hours
- Auto-refresh: every 60 seconds
- Uses classic TSVB/aggregation-based visualizations (not Lens — Lens had import issues on ES 8.17)

### 8. Cowrie Event Types Reference

| Event ID | What It Captures |
|----------|-----------------|
| `cowrie.session.connect` | New TCP connection (source IP, port, protocol) |
| `cowrie.client.version` | SSH client version string |
| `cowrie.client.kex` | Key exchange algorithms, HASSH fingerprint |
| `cowrie.client.fingerprint` | SSH public key fingerprint |
| `cowrie.login.failed` | Failed auth attempt (username + password or key) |
| `cowrie.login.success` | Honeypot accepted credentials — attacker enters fake shell (see Section 2) |
| `cowrie.command.input` | Commands typed by attacker after login |
| `cowrie.command.failed` | Commands that Cowrie couldn't emulate |
| `cowrie.session.file_download` | Files downloaded by attacker (stored in `/opt/cowrie/data/`, auto-cleaned after 3 days) |
| `cowrie.session.closed` | Session ended (includes duration) |
| `cowrie.session.params` | Terminal parameters (width, height, etc.) |
| `cowrie.client.var` | Environment variables from client |
| `cowrie.log.closed` | Transcript log file closed |

## Operational Runbook

### Check probe health

Via Tailscale (from a machine on the tailnet):
```bash
ssh -p 2222 sixigma@100.108.213.106 '
  sudo docker ps
  sudo systemctl is-active filebeat
  tailscale status
  wc -l /opt/cowrie/log/cowrie.json
  df -h /
  free -m
'
```

Via jump host (from WSL through ELK machine):
```bash
ssh -J sixigma@192.168.0.148 -p 2222 -i ~/.ssh/google_compute_engine sixigma@100.108.213.106 '...'
```

### Check ES data volume
```bash
curl -s -u elastic:<password> "http://192.168.0.148:9200/.ds-cowrie-*/_count"
```

### Check aggregated attack stats
```bash
curl -s -u elastic:<password> "http://192.168.0.148:9200/.ds-cowrie-*/_search" \
  -H "Content-Type: application/json" -d '{
    "size": 0,
    "aggs": {
      "event_types": {"terms": {"field": "eventid", "size": 20}},
      "unique_ips": {"cardinality": {"field": "source.ip"}},
      "unique_sessions": {"cardinality": {"field": "session"}}
    }
  }'
```

### Restart Cowrie
```bash
ssh -p 2222 sixigma@100.108.213.106 '
  sudo docker restart cowrie
  sleep 3
  sudo docker logs cowrie --tail 5
'
```

### Restart ELK containers
```bash
ssh sixigma@192.168.0.148 '
  sudo docker restart elasticsearch
  sleep 30  # ES needs time to initialize
  sudo docker restart kibana
  sleep 20
  sudo docker restart logstash
  curl -s -u elastic:<password> "http://localhost:9200/_cluster/health" | python3 -m json.tool
'
```

### Troubleshooting: Filebeat running but ES count not increasing

1. Check Filebeat logs: `sudo journalctl -u filebeat -n 20 --no-pager`
2. Check Tailscale connectivity: `tailscale ping elk-xps`
3. Check ES health: `curl -s -u elastic:<password> http://100.101.38.12:9200/_cluster/health`
4. Check if log file is being written: `tail -1 /opt/cowrie/log/cowrie.json`
5. If Tailscale is disconnected, restart: `sudo tailscale up`

### Troubleshooting: Cowrie not receiving connections

1. Verify firewall: `gcloud compute firewall-rules list --filter="name:honeypot"`
2. Verify port binding: `sudo ss -tlnp | grep -E ':22 |:23 '`
3. Check Docker: `sudo docker logs cowrie --tail 20`
4. Test externally: `ssh -o ConnectTimeout=3 root@34.80.234.119` (should get Cowrie banner)

## Future: EoP Integration Plan

This infrastructure is the foundation for a composite threat criterion in EoP:

1. **HoneypotCollector** — New collector in EoP that queries ES for attack metrics on a 10-minute interval. Metrics to track: event count per window, unique source IPs, unique sessions, login attempt rate, and command execution count. The surge signal should be based on **unique source IPs per 1-hour window** compared to the 7-day median — this is more meaningful than raw event count (which one botnet can inflate).
2. **3-tier composite criterion** — Correlates honeypot surge with MERIT-NT signal degradation:
   - `canary`: honeypot surge only (>3x 7-day median unique IPs, sustained 20+ min)
   - `suspected_regional_pressure`: surge + TW MERIT-NT warning/degraded
   - `probable_coordinated_disruption`: surge + TW MERIT-NT critical + corroborator (BGP, news, military)
3. **Cross-domain correlation** — Military overlay (PLAAF activity), market panic (Polymarket, Fear & Greed), news amplification.

See the full feature plan in Claude Code project memory (persisted across sessions, not in repo).

## Cost Tracking

| Item | Monthly Cost | Notes |
|------|-------------|-------|
| GCP e2-micro VM (asia-east1) | ~$6.11 | Billable — free tier only for `us-central1`, `us-west1`, `us-east1` |
| 10GB standard persistent disk | ~$0.40 | |
| Network egress (Tailscale log shipping) | ~$0.50 | Estimate based on ~2,500 events/day × ~500 bytes each ≈ 1.25 MB/day. Heavy attack days may increase this but unlikely to exceed $1/mo |
| Tailscale | Free | Personal plan, up to 100 devices |
| ELK stack (self-hosted on XPS) | $0 | |
| **Total** | **~$7.01 / $10 budget** | |

## Security Considerations

1. **Honeypot is internet-facing by design** — ports 22/23 must be open. This is inherent to how honeypots work.
2. **Tailscale ACLs should be configured** to restrict the probe's network access (see Section 5).
3. **Docker resource limits** are in place to prevent a compromised Cowrie from consuming all VM resources.
4. **Admin SSH (port 2222)** is restricted to Tailscale CGNAT range only — not reachable from the public internet.
5. **ES credentials** should be scoped down from the `elastic` superuser to a dedicated writer role.
6. **SA key rotation** — the GCP service account key is long-lived. Rotate if compromised; consider Workload Identity Federation for keyless auth.
7. **Malware downloads** are auto-cleaned after 3 days and isolated inside the Docker container.
