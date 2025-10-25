from fastapi import FastAPI, Request, Form, Response, HTTPException, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from itsdangerous import URLSafeTimedSerializer, BadSignature
from sqlalchemy.orm import Session
from typing import Optional
import secrets
import os
from datetime import datetime, timedelta

# Import database functions
from database import get_db, authenticate_user, init_db

# Initialize database on startup
init_db()

# Environment detection for cookie security
IS_PRODUCTION = os.getenv("ENVIRONMENT", "development") == "production"

# Rate limiter
limiter = Limiter(key_func=get_remote_address)
app = FastAPI()
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


# Security headers middleware
@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    """Add security headers to all responses"""
    response = await call_next(request)

    # HSTS: Force HTTPS for 1 year (only works when served over HTTPS)
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"

    # Prevent MIME type sniffing
    response.headers["X-Content-Type-Options"] = "nosniff"

    # Prevent clickjacking
    response.headers["X-Frame-Options"] = "DENY"

    # Enable XSS filter
    response.headers["X-XSS-Protection"] = "1; mode=block"

    # Referrer policy
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

    return response


# Templates
templates = Jinja2Templates(directory="templates")

# CSRF protection
SECRET_KEY = secrets.token_urlsafe(32)  # In production, store this securely
csrf_serializer = URLSafeTimedSerializer(SECRET_KEY)

# Simple session storage (in production, use Redis or database)
sessions = {}

# Login attempt tracking for rate limiting
login_attempts = {}  # {ip: [timestamp1, timestamp2, ...]}


def generate_csrf_token() -> str:
    """Generate a CSRF token"""
    return csrf_serializer.dumps(secrets.token_urlsafe(16))


def validate_csrf_token(token: str, max_age: int = 3600) -> bool:
    """Validate a CSRF token (valid for 1 hour by default)"""
    try:
        csrf_serializer.loads(token, max_age=max_age)
        return True
    except BadSignature:
        return False


def get_client_ip(request: Request) -> str:
    """Get real client IP (works behind Cloudflare and other proxies)"""
    # Cloudflare sets CF-Connecting-IP header
    cf_ip = request.headers.get("CF-Connecting-IP")
    if cf_ip:
        return cf_ip

    # Fallback to X-Forwarded-For
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()

    # Fallback to X-Real-IP
    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip

    # Fallback to direct connection
    return request.client.host if request.client else "unknown"


def check_rate_limit(ip: str, max_attempts: int = 5, window_minutes: int = 15) -> bool:
    """Check if an IP has exceeded the rate limit for login attempts"""
    now = datetime.now()
    cutoff_time = now - timedelta(minutes=window_minutes)

    # Clean old attempts
    if ip in login_attempts:
        login_attempts[ip] = [t for t in login_attempts[ip] if t > cutoff_time]
    else:
        login_attempts[ip] = []

    # Check if limit exceeded
    if len(login_attempts[ip]) >= max_attempts:
        return False

    return True


def record_login_attempt(ip: str):
    """Record a login attempt"""
    if ip not in login_attempts:
        login_attempts[ip] = []
    login_attempts[ip].append(datetime.now())


def create_session(username: str) -> str:
    """Create a session token for a user"""
    session_token = secrets.token_urlsafe(32)
    sessions[session_token] = username
    return session_token


def get_current_user(request: Request) -> Optional[str]:
    """Get current user from session cookie"""
    session_token = request.cookies.get("session_token")
    if session_token and session_token in sessions:
        return sessions[session_token]
    return None


@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    """Redirect to login or index based on authentication"""
    user = get_current_user(request)
    if user:
        return RedirectResponse(url="/index", status_code=302)
    return RedirectResponse(url="/login", status_code=302)


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    """Display login page"""
    user = get_current_user(request)
    if user:
        return RedirectResponse(url="/index", status_code=302)

    # Generate CSRF token
    csrf_token = generate_csrf_token()

    return templates.TemplateResponse("login.html", {
        "request": request,
        "csrf_token": csrf_token
    })


@app.post("/login")
@limiter.limit("10/minute")  # Rate limit: 10 requests per minute per IP
async def login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    csrf_token: str = Form(...),
    db: Session = Depends(get_db)
):
    """Handle login form submission"""
    # Get client IP (works behind Cloudflare/proxies)
    client_ip = get_client_ip(request)

    # Validate CSRF token
    if not validate_csrf_token(csrf_token):
        csrf_token_new = generate_csrf_token()
        return templates.TemplateResponse(
            "login.html",
            {
                "request": request,
                "error": "Invalid or expired CSRF token. Please try again.",
                "csrf_token": csrf_token_new
            }
        )

    # Check rate limit (5 failed attempts per 15 minutes)
    if not check_rate_limit(client_ip):
        csrf_token_new = generate_csrf_token()
        return templates.TemplateResponse(
            "login.html",
            {
                "request": request,
                "error": "Too many login attempts. Please try again in 15 minutes.",
                "csrf_token": csrf_token_new
            }
        )

    # Verify credentials using database
    user = authenticate_user(db, username, password)
    if user:
        # Successful login - clear login attempts
        if client_ip in login_attempts:
            del login_attempts[client_ip]

        # Create session
        session_token = create_session(username)

        # Redirect to index with session cookie
        response = RedirectResponse(url="/index", status_code=302)
        response.set_cookie(
            key="session_token",
            value=session_token,
            httponly=True,
            secure=IS_PRODUCTION,    # Only send over HTTPS in production
            samesite="strict" if IS_PRODUCTION else "lax",  # Strict in production, lax for local dev
            max_age=3600        # 1 hour
        )
        return response
    else:
        # Failed login - record attempt
        record_login_attempt(client_ip)

        # Generate new CSRF token
        csrf_token_new = generate_csrf_token()

        # Invalid credentials
        return templates.TemplateResponse(
            "login.html",
            {
                "request": request,
                "error": "Invalid username or password",
                "csrf_token": csrf_token_new
            }
        )


@app.get("/index", response_class=HTMLResponse)
async def index(request: Request):
    """Display index page (requires authentication)"""
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    return templates.TemplateResponse("index.html", {"request": request, "username": user})


@app.get("/logout")
async def logout(request: Request):
    """Logout user and destroy session"""
    session_token = request.cookies.get("session_token")
    if session_token and session_token in sessions:
        del sessions[session_token]

    response = RedirectResponse(url="/login", status_code=302)
    response.delete_cookie("session_token")
    return response


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
