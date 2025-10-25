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

## Installation

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

## Project Structure

```
fastapi-login-app/
├── main.py                      # FastAPI application
├── database.py                  # Database models and functions
├── manage_users.py              # User management CLI tool
├── templates/
│   ├── login.html              # Login page
│   └── index.html              # Dashboard page
├── users.db                    # SQLite database (excluded from git)
├── venv/                       # Virtual environment
├── SECURITY.md                 # Security documentation
├── USER_MANAGEMENT.md          # User management guide
├── CLOUDFLARE_TUNNEL_SETUP.md  # HTTPS setup guide
└── README.md                   # This file
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
