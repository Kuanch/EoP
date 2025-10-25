# FastAPI Login Application

A simple web application with login authentication built with FastAPI.

## Features

- Login page with beautiful UI
- Session-based authentication with SQLite database
- Dashboard page after login
- Logout functionality
- Protected routes
- User management CLI tool

## Security Features

- ✅ Password hashing with bcrypt
- ✅ CSRF protection
- ✅ Rate limiting (endpoint + login attempts)
- ✅ HTTPS/TLS support (via Cloudflare Tunnel)
- ✅ Security headers (HSTS, X-Frame-Options, etc.)
- ✅ Secure cookies (httponly, secure, samesite)
- ✅ Real IP detection behind proxies
- ✅ SQLite database for user management

See `SECURITY.md` for detailed documentation and `USER_MANAGEMENT.md` for user management guide.

## User Management

Users are now stored in SQLite database instead of hardcoded credentials. Use the CLI tool to manage users:

```bash
# Initialize database (first time only)
venv/bin/python manage_users.py init

# Create a user
venv/bin/python manage_users.py create admin

# List all users
venv/bin/python manage_users.py list
```

See `USER_MANAGEMENT.md` for complete documentation.

## Quick Start with Docker (Recommended)

The easiest way to run the application on any computer:

```bash
# 1. Clone the repository
git clone https://github.com/Kuanch/EoP.git
cd EoP

# 2. Create data directory
mkdir -p data

# 3. Build and start the application
docker-compose up -d

# 4. Create admin user (first time only)
docker exec -it fastapi-login-app python manage_users.py init
docker exec -it fastapi-login-app python manage_users.py create admin

# 5. Access the application
# Open http://localhost:8000 in your browser
```

To stop the application:
```bash
docker-compose down
```

To view logs:
```bash
docker-compose logs -f app
```

## Installation (Without Docker)

1. Create a virtual environment:
```bash
python3 -m venv venv
```

2. Activate the virtual environment:
```bash
source venv/bin/activate  # On Linux/Mac
```

3. Install dependencies:
```bash
pip install fastapi uvicorn python-multipart jinja2 bcrypt slowapi itsdangerous sqlalchemy
```

4. Initialize the database and create a user:
```bash
venv/bin/python manage_users.py init
venv/bin/python manage_users.py create admin
```

## Running the Application

```bash
python main.py
```

Or with uvicorn directly:
```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

The application will be available at: http://localhost:8000

## HTTPS with Cloudflare Tunnel

To expose your application securely with HTTPS:

```bash
# Quick test (temporary URL)
cloudflared tunnel --url http://localhost:8000

# Production setup (requires Cloudflare account)
# See CLOUDFLARE_TUNNEL_SETUP.md for detailed instructions
```

For full setup instructions, see `CLOUDFLARE_TUNNEL_SETUP.md`.

## Docker Deployment

### Basic Usage

The application includes Docker support for easy deployment:

```bash
# Build and run
docker-compose up -d

# Initialize database and create first user
docker exec -it fastapi-login-app python manage_users.py init
docker exec -it fastapi-login-app python manage_users.py create admin

# View logs
docker-compose logs -f app

# Stop
docker-compose down
```

### Scaling Options

The `docker-compose.yml` includes commented sections for horizontal scaling:

1. **Redis for Session Storage**: Uncomment the `redis` service to enable shared session storage across multiple app instances
2. **PostgreSQL**: Uncomment the `postgres` service to replace SQLite for production deployments
3. **Nginx Load Balancer**: Uncomment the `nginx` service to distribute traffic across multiple app instances
4. **Cloudflare Tunnel**: Uncomment the `cloudflared` service to enable automatic HTTPS

### Data Persistence

Database is stored in `./data/users.db` (mounted as volume), so data persists across container restarts.

### Environment Variables

Configure via environment variables:

- `DATABASE_URL`: Database connection string (default: `sqlite:///./data/users.db`)
- `ENVIRONMENT`: Set to `production` for production mode
- `CLOUDFLARE_TUNNEL_TOKEN`: For Cloudflare Tunnel (optional)

## Project Structure

```
fastapi-login-app/
├── main.py                      # FastAPI application
├── database.py                  # Database models and functions
├── manage_users.py              # User management CLI tool
├── templates/
│   ├── login.html              # Login page
│   └── index.html              # Dashboard page
├── Dockerfile                  # Docker image definition
├── docker-compose.yml          # Docker orchestration
├── requirements.txt            # Python dependencies
├── .dockerignore              # Docker build exclusions
├── data/                      # Database directory (volume mount)
│   └── users.db              # SQLite database
├── venv/                      # Virtual environment (not in Docker)
├── SECURITY.md                # Security documentation
├── USER_MANAGEMENT.md         # User management guide
├── CLOUDFLARE_TUNNEL_SETUP.md # HTTPS setup guide
└── README.md                  # This file
```

## Security Status

**Implemented (4/10):**
- ✅ Password hashing with bcrypt
- ✅ CSRF protection
- ✅ Rate limiting
- ✅ HTTPS/TLS (via Cloudflare Tunnel)

**Remaining (6/10):**
- ⏳ Secure session management (Redis/database)
- ⏳ Security headers (HSTS, X-Frame-Options - partially done)
- ⏳ Input validation
- ⏳ Audit logging
- ⏳ Account lockout
- ⏳ Additional secure cookie improvements

See `SECURITY.md` for implementation details and `CLOUDFLARE_TUNNEL_SETUP.md` for HTTPS setup.
