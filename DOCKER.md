# Docker Deployment Guide

Complete guide for deploying the FastAPI login application using Docker and Docker Compose.

## Quick Start

```bash
# 1. Clone repository
git clone https://github.com/Kuanch/EoP.git
cd EoP

# 2. Create environment file
cp .env.example .env
nano .env  # Edit with your settings

# 3. Create data directory
mkdir -p data

# 4. Start services
docker-compose up -d

# 5. Initialize database and create user
docker exec -it fastapi-login-app python manage_users.py init
docker exec -it fastapi-login-app python manage_users.py create admin

# 6. Access application
# Open http://localhost:8000
```

---

## Environment Configuration

### Step 1: Create .env File

Copy the example and edit it:

```bash
cp .env.example .env
```

### Step 2: Configure Variables

Edit `.env` with your settings:

```bash
# Application Settings
ENVIRONMENT=production

# Database (default SQLite)
DATABASE_URL=sqlite:///./data/users.db

# Cloudflare Tunnel Token (optional, for HTTPS)
CLOUDFLARE_TUNNEL_TOKEN=your_actual_token_here

# PostgreSQL Password (if using postgres service)
POSTGRES_PASSWORD=your_secure_password
```

### Getting Cloudflare Tunnel Token

There are two ways to use Cloudflare Tunnel with Docker:

#### Method 1: Using Tunnel Token (Recommended for Docker)

1. Go to [Cloudflare Zero Trust Dashboard](https://one.dash.cloudflare.com/)
2. Navigate to **Access** → **Tunnels**
3. Create a new tunnel or select existing one
4. Click **Configure** → **Public Hostname**
5. Add a public hostname pointing to `http://app:8000`
6. Go back to tunnel overview, click on the tunnel name
7. Copy the **Tunnel Token** (starts with `eyJh...`)
8. Add to `.env` file:
   ```
   CLOUDFLARE_TUNNEL_TOKEN=eyJh...your_token_here
   ```

#### Method 2: Using Tunnel Credentials (Alternative)

If you already have a tunnel configured with credentials file:

1. Locate your tunnel credentials: `~/.cloudflared/<UUID>.json`
2. Mount it as volume in `docker-compose.yml`:
   ```yaml
   cloudflared:
     volumes:
       - ~/.cloudflared:/etc/cloudflared:ro
     command: tunnel --no-autoupdate run <tunnel-name>
   ```

---

## Docker Compose Services

### Main Application (app)

Always running. The FastAPI application.

```yaml
services:
  app:
    # ... configuration in docker-compose.yml
```

**Ports**: 8000
**Volumes**:
- `./data:/app/data` - Database persistence
- `./templates:/app/templates:ro` - Template updates without rebuild

### Cloudflare Tunnel (cloudflared)

**Optional** - Uncomment to enable HTTPS access.

```yaml
# In docker-compose.yml, uncomment:
cloudflared:
  image: cloudflare/cloudflared:latest
  container_name: cloudflared-tunnel
  command: tunnel --no-autoupdate run --token ${CLOUDFLARE_TUNNEL_TOKEN}
  env_file:
    - .env
  restart: unless-stopped
  networks:
    - app-network
  depends_on:
    - app
```

**Requirements**:
1. Set `CLOUDFLARE_TUNNEL_TOKEN` in `.env`
2. Configure public hostname to point to `http://app:8000`
3. Uncomment the service in `docker-compose.yml`

### Redis (redis)

**Optional** - For session storage when scaling to multiple app instances.

```yaml
# Uncomment in docker-compose.yml when needed
redis:
  image: redis:7-alpine
  # ... rest of configuration
```

**When to use**: Multiple app instances behind load balancer

### PostgreSQL (postgres)

**Optional** - Replace SQLite for production with multiple instances.

```yaml
# Uncomment in docker-compose.yml when needed
postgres:
  image: postgres:16-alpine
  # ... rest of configuration
```

**When to use**:
- Production deployments
- Multiple app instances
- Need for concurrent writes

**Setup**:
1. Uncomment `postgres` service
2. Uncomment `postgres-data` volume
3. Set `POSTGRES_PASSWORD` in `.env`
4. Update `DATABASE_URL` in `.env`:
   ```
   DATABASE_URL=postgresql://fastapi:your_password@postgres:5432/fastapi_users
   ```

### Nginx (nginx)

**Optional** - Load balancer for multiple app instances.

**When to use**: Horizontal scaling with multiple app containers

---

## Common Operations

### Start Services

```bash
# Start in background
docker-compose up -d

# Start with logs visible
docker-compose up

# Start specific service
docker-compose up -d app
```

### Stop Services

```bash
# Stop all services
docker-compose down

# Stop and remove volumes (WARNING: deletes database!)
docker-compose down -v

# Stop specific service
docker-compose stop app
```

### View Logs

```bash
# All services
docker-compose logs -f

# Specific service
docker-compose logs -f app
docker-compose logs -f cloudflared

# Last 100 lines
docker-compose logs --tail=100 app
```

### Restart Services

```bash
# Restart all
docker-compose restart

# Restart specific service
docker-compose restart app
```

### Rebuild After Code Changes

```bash
# Rebuild and restart
docker-compose up -d --build

# Force rebuild (no cache)
docker-compose build --no-cache
docker-compose up -d
```

### Execute Commands in Container

```bash
# Interactive shell
docker exec -it fastapi-login-app /bin/bash

# Run manage_users.py commands
docker exec -it fastapi-login-app python manage_users.py list
docker exec -it fastapi-login-app python manage_users.py create username
docker exec -it fastapi-login-app python manage_users.py password username

# Check database
docker exec -it fastapi-login-app ls -lh /app/data/
```

---

## Scaling Scenarios

### Scenario 1: Single Instance (Default)

**Use case**: Small deployments, <100 concurrent users

**Configuration**:
- App service only
- SQLite database
- Optional: Cloudflare Tunnel for HTTPS

```bash
docker-compose up -d
```

### Scenario 2: HTTPS with Cloudflare Tunnel

**Use case**: Public access with HTTPS

**Steps**:
1. Add `CLOUDFLARE_TUNNEL_TOKEN` to `.env`
2. Uncomment `cloudflared` service in `docker-compose.yml`
3. Start services:
   ```bash
   docker-compose up -d
   ```

### Scenario 3: Multiple Instances with Load Balancer

**Use case**: High traffic, horizontal scaling

**Steps**:
1. Uncomment `redis` service (for shared sessions)
2. Uncomment `postgres` service (for shared database)
3. Uncomment `nginx` service (for load balancing)
4. Update `.env`:
   ```
   DATABASE_URL=postgresql://fastapi:password@postgres:5432/fastapi_users
   POSTGRES_PASSWORD=your_secure_password
   ```
5. Scale app instances:
   ```bash
   docker-compose up -d --scale app=3
   ```

---

## Data Persistence

### Database Location

- **SQLite**: `./data/users.db` (mounted from host)
- **PostgreSQL**: Docker volume `postgres-data`

### Backup Database

**SQLite**:
```bash
# Backup
cp data/users.db data/users.db.backup-$(date +%Y%m%d)

# Restore
cp data/users.db.backup-20250125 data/users.db
docker-compose restart app
```

**PostgreSQL**:
```bash
# Backup
docker exec postgres-db pg_dump -U fastapi fastapi_users > backup.sql

# Restore
cat backup.sql | docker exec -i postgres-db psql -U fastapi fastapi_users
```

### Volume Management

```bash
# List volumes
docker volume ls

# Inspect volume
docker volume inspect fastapi-login-app_postgres-data

# Backup volume
docker run --rm -v fastapi-login-app_postgres-data:/data -v $(pwd):/backup alpine tar czf /backup/postgres-backup.tar.gz -C /data .

# Restore volume
docker run --rm -v fastapi-login-app_postgres-data:/data -v $(pwd):/backup alpine tar xzf /backup/postgres-backup.tar.gz -C /data
```

---

## Troubleshooting

### Port Already in Use

**Error**: `Bind for 0.0.0.0:8000 failed: port is already allocated`

**Solution**:
```bash
# Find process using port 8000
lsof -i :8000
# or
netstat -tulpn | grep 8000

# Kill the process or change port in docker-compose.yml
ports:
  - "8001:8000"  # Map to different host port
```

### Container Keeps Restarting

**Check logs**:
```bash
docker-compose logs app
```

**Common causes**:
1. Database initialization failed
2. Missing environment variables
3. Port conflict

**Solution**:
```bash
# Stop and remove containers
docker-compose down

# Check .env file exists and is valid
cat .env

# Recreate containers
docker-compose up -d
```

### Database Not Persisting

**Check volume mount**:
```bash
docker inspect fastapi-login-app | grep -A 10 Mounts
```

**Ensure data directory exists**:
```bash
mkdir -p data
chmod 755 data
docker-compose restart app
```

### Cloudflare Tunnel Not Working

**Check token**:
```bash
# Verify token is set
docker exec cloudflared-tunnel env | grep CLOUDFLARE

# Check logs
docker-compose logs cloudflared
```

**Common issues**:
1. Invalid token in `.env`
2. Tunnel not configured to point to `http://app:8000`
3. Firewall blocking outbound connections

**Solution**:
1. Verify token in Cloudflare dashboard
2. Check tunnel configuration points to internal DNS name `app` (not `localhost`)
3. Restart cloudflared:
   ```bash
   docker-compose restart cloudflared
   ```

### Cannot Access Application

**Check container is running**:
```bash
docker-compose ps
```

**Test from inside container**:
```bash
docker exec -it fastapi-login-app curl http://localhost:8000/login
```

**Test from host**:
```bash
curl http://localhost:8000/login
```

**Check firewall**:
```bash
# On Linux
sudo ufw status
sudo ufw allow 8000

# On Windows/WSL
# Check Windows Firewall settings
```

---

## Security Best Practices

### 1. Protect .env File

```bash
# Never commit .env to git
echo ".env" >> .gitignore

# Set proper permissions
chmod 600 .env
```

### 2. Use Strong Passwords

Generate secure passwords:
```bash
# For PostgreSQL
openssl rand -base64 32

# For session secret
openssl rand -hex 32
```

### 3. Update Images Regularly

```bash
# Pull latest images
docker-compose pull

# Rebuild with latest base images
docker-compose build --pull
docker-compose up -d
```

### 4. Use Docker Secrets (Production)

For production deployments, use Docker Swarm secrets instead of .env:

```yaml
secrets:
  cloudflare_token:
    external: true

services:
  cloudflared:
    secrets:
      - cloudflare_token
    command: tunnel --no-autoupdate run --token-file /run/secrets/cloudflare_token
```

### 5. Limit Container Privileges

Already configured with:
- Non-root user (planned enhancement)
- Read-only root filesystem where possible
- Health checks
- Restart policies

---

## Production Checklist

Before deploying to production:

- [ ] Set `ENVIRONMENT=production` in `.env`
- [ ] Use strong `POSTGRES_PASSWORD` (if using PostgreSQL)
- [ ] Set `chmod 600 .env` to protect secrets
- [ ] Configure Cloudflare Tunnel for HTTPS
- [ ] Set up database backups (cron job)
- [ ] Configure logging (see docker-compose logs)
- [ ] Set up monitoring (Prometheus + Grafana)
- [ ] Review and adjust health check intervals
- [ ] Test disaster recovery (restore from backup)
- [ ] Document your specific configuration
- [ ] Set up automated updates (Watchtower)

---

## Advanced Configuration

### Custom Network

```yaml
# In docker-compose.yml
networks:
  app-network:
    driver: bridge
    ipam:
      config:
        - subnet: 172.20.0.0/16
```

### Resource Limits

```yaml
services:
  app:
    deploy:
      resources:
        limits:
          cpus: '0.5'
          memory: 512M
        reservations:
          cpus: '0.25'
          memory: 256M
```

### Custom DNS

```yaml
services:
  app:
    dns:
      - 8.8.8.8
      - 1.1.1.1
```

---

## Getting Help

- **Docker Docs**: https://docs.docker.com/
- **Cloudflare Tunnel**: https://developers.cloudflare.com/cloudflare-one/connections/connect-apps/
- **FastAPI**: https://fastapi.tiangolo.com/
- **Project Issues**: https://github.com/Kuanch/EoP/issues
