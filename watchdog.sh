#!/bin/bash
# EoP Watchdog — ensures all services are running
# Add to crontab: * * * * * /home/sixigma/EoP/watchdog.sh >> /tmp/eop-watchdog.log 2>&1

LOG_PREFIX="[$(date '+%Y-%m-%d %H:%M:%S')]"

# 1. EoP server
if ! systemctl is-active --quiet eop; then
    echo "$LOG_PREFIX EoP down, restarting..."
    systemctl restart eop
fi

# 2. Cloudflare tunnel
if ! systemctl is-active --quiet cloudflared; then
    echo "$LOG_PREFIX Cloudflared down, restarting..."
    systemctl restart cloudflared
fi

# 3. ntfy Docker container
if ! docker ps --format '{{.Names}}' | grep -q eop-ntfy; then
    echo "$LOG_PREFIX ntfy container down, restarting..."
    docker compose -f /home/sixigma/EoP/docker-compose.ntfy.yml up -d
fi

# 4. Verify EoP is actually responding (not just process alive)
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 http://localhost:8000/ 2>/dev/null)
if [ "$HTTP_CODE" != "302" ] && [ "$HTTP_CODE" != "200" ]; then
    echo "$LOG_PREFIX EoP not responding (HTTP $HTTP_CODE), restarting..."
    systemctl restart eop
fi
