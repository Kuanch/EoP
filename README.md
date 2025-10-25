# FastAPI Login Application

A simple web application with login authentication built with FastAPI.

## Features

- Login page with beautiful UI
- Session-based authentication
- Dashboard page after login
- Logout functionality
- Protected routes

## Security Features

- ✅ Password hashing with bcrypt
- ✅ CSRF protection
- ✅ Rate limiting (endpoint + login attempts)
- ✅ HTTPS/TLS support (via Cloudflare Tunnel)
- ✅ Security headers (HSTS, X-Frame-Options, etc.)
- ✅ Secure cookies (httponly, secure, samesite)
- ✅ Real IP detection behind proxies

See `SECURITY.md` for detailed documentation.

## Current Credentials

- **Username**: admin
- **Password**: password

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
pip install fastapi uvicorn python-multipart jinja2 bcrypt slowapi itsdangerous
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
├── main.py              # FastAPI application
├── templates/
│   ├── login.html      # Login page
│   └── index.html      # Dashboard page
├── static/             # Static files (CSS, JS, images)
├── venv/               # Virtual environment
└── README.md           # This file
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
