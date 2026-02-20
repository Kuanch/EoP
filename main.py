import asyncio
import logging
import os
import secrets
import time
from datetime import datetime, timedelta
from typing import Optional

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, Request, Form, Depends, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from itsdangerous import URLSafeTimedSerializer, BadSignature
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from sqlalchemy.orm import Session

from database import get_db, authenticate_user, init_db, SessionLocal, Article
from ws_manager import manager

# Enhanced logging with security events
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

# Security-specific logger
security_logger = logging.getLogger("security")
security_handler = logging.FileHandler("logs/security.log")
security_formatter = logging.Formatter("%(asctime)s SECURITY %(levelname)s: %(message)s")
security_handler.setFormatter(security_formatter)
security_logger.addHandler(security_handler)
security_logger.setLevel(logging.WARNING)

# Initialize database on startup
init_db()

# Environment detection
IS_PRODUCTION = os.getenv("ENVIRONMENT", "development") == "production"

# Rate limiter
limiter = Limiter(key_func=get_remote_address)
app = FastAPI()
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Security middleware
@app.middleware("http")
async def security_middleware(request: Request, call_next):
    client_ip = get_client_ip(request)

    # Detect suspicious patterns
    if _detect_attack_patterns(request):
        security_logger.error(f"ATTACK_ATTEMPT detected from {client_ip}: {request.url}")
        return JSONResponse({"error": "Forbidden"}, status_code=403)

    # Protect sensitive static files - require authentication for JS/CSS
    if request.url.path.startswith(("/static/js/", "/static/css/")):
        if not _require_auth_simple(request):
            security_logger.warning(f"Unauthorized static file access attempt from {client_ip}: {request.url.path}")
            return JSONResponse({"error": "Unauthorized"}, status_code=401)

    # Protect API endpoints - require authentication
    if request.url.path.startswith("/api/"):
        if not _require_auth_simple(request):
            security_logger.warning(f"Unauthorized API access attempt from {client_ip}: {request.url.path}")
            return JSONResponse({"error": "Unauthorized"}, status_code=401)

    response = await call_next(request)

    # Security headers
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' https://unpkg.com; "
        "style-src 'self' 'unsafe-inline' https://unpkg.com; "
        "img-src 'self' data: https:; "
        "connect-src 'self' wss: ws:; "
        "frame-ancestors 'none'"
    )
    return response

# Templates
templates = Jinja2Templates(directory="templates")

# CSRF protection — persist SECRET_KEY across restarts
SECRET_KEY = os.getenv("SECRET_KEY", "")
if not SECRET_KEY:
    # Auto-generate and save to .env for persistence
    SECRET_KEY = secrets.token_urlsafe(32)
    _env_path = os.path.join(os.path.dirname(__file__), ".env")
    try:
        with open(_env_path, "a") as f:
            f.write(f"\nSECRET_KEY={SECRET_KEY}\n")
        logger.info("Generated and saved SECRET_KEY to .env")
    except OSError:
        logger.warning("Could not save SECRET_KEY to .env — CSRF tokens will reset on restart")
csrf_serializer = URLSafeTimedSerializer(SECRET_KEY)

# Session storage — DB-backed, survives restarts
SESSION_MAX_AGE = 86400  # 24 hours

# Enhanced login attempt tracking with lockout
login_attempts = {}
MAX_LOGIN_ATTEMPTS = 5
LOCKOUT_DURATION = 3600  # 1 hour in seconds


def generate_csrf_token() -> str:
    return csrf_serializer.dumps(secrets.token_urlsafe(16))


def validate_csrf_token(token: str, max_age: int = 3600) -> bool:
    try:
        csrf_serializer.loads(token, max_age=max_age)
        return True
    except BadSignature:
        return False


def get_client_ip(request: Request) -> str:
    cf_ip = request.headers.get("CF-Connecting-IP")
    if cf_ip:
        return cf_ip
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip
    return request.client.host if request.client else "unknown"


def check_rate_limit(ip: str, max_attempts: int = MAX_LOGIN_ATTEMPTS, window_minutes: int = 15) -> bool:
    """Enhanced rate limiting with progressive delays and lockout."""
    now = datetime.now()
    cutoff_time = now - timedelta(minutes=window_minutes)

    if ip in login_attempts:
        # Clean old attempts
        login_attempts[ip] = [t for t in login_attempts[ip] if t > cutoff_time]

        # Check for lockout
        if len(login_attempts[ip]) >= max_attempts:
            # Apply lockout duration
            lockout_cutoff = now - timedelta(seconds=LOCKOUT_DURATION)
            if login_attempts[ip][-1] > lockout_cutoff:
                return False
    else:
        login_attempts[ip] = []

    return len(login_attempts[ip]) < max_attempts


def record_login_attempt(ip: str):
    """Record failed login attempt with security logging."""
    if ip not in login_attempts:
        login_attempts[ip] = []
    login_attempts[ip].append(datetime.now())

    # Log security event
    attempt_count = len(login_attempts[ip])
    security_logger.warning(f"Failed login attempt #{attempt_count} from IP {ip}")

    if attempt_count >= MAX_LOGIN_ATTEMPTS:
        security_logger.error(f"SECURITY ALERT: Account lockout triggered for IP {ip} after {attempt_count} failed attempts")


def create_session(username: str) -> str:
    from database import SessionToken
    session_token = secrets.token_urlsafe(32)
    db = SessionLocal()
    try:
        db.add(SessionToken(token=session_token, username=username, created_at=time.time()))
        db.commit()
    finally:
        db.close()
    return session_token


def get_current_user(request: Request) -> Optional[str]:
    from database import SessionToken
    session_token = request.cookies.get("session_token")
    if not session_token:
        return None
    db = SessionLocal()
    try:
        s = db.query(SessionToken).filter(SessionToken.token == session_token).first()
        if not s:
            return None
        if time.time() - s.created_at > SESSION_MAX_AGE:
            db.delete(s)
            db.commit()
            return None
        return s.username
    finally:
        db.close()


def _delete_session(token: str):
    from database import SessionToken
    db = SessionLocal()
    try:
        s = db.query(SessionToken).filter(SessionToken.token == token).first()
        if s:
            db.delete(s)
            db.commit()
    finally:
        db.close()


def _cleanup_expired_sessions():
    """Remove expired sessions."""
    from database import SessionToken
    db = SessionLocal()
    try:
        cutoff = time.time() - SESSION_MAX_AGE
        db.query(SessionToken).filter(SessionToken.created_at < cutoff).delete()
        db.commit()
    finally:
        db.close()


# --- Routes ---

@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    user = get_current_user(request)
    if user:
        return RedirectResponse(url="/dashboard", status_code=302)
    return RedirectResponse(url="/login", status_code=302)


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    user = get_current_user(request)
    if user:
        return RedirectResponse(url="/dashboard", status_code=302)
    csrf_token = generate_csrf_token()
    return templates.TemplateResponse("login.html", {"request": request, "csrf_token": csrf_token})


@app.post("/login")
@limiter.limit("10/minute")
async def login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    csrf_token: str = Form(...),
    db: Session = Depends(get_db)
):
    client_ip = get_client_ip(request)

    if not validate_csrf_token(csrf_token):
        csrf_token_new = generate_csrf_token()
        return templates.TemplateResponse("login.html", {
            "request": request, "error": "Invalid or expired CSRF token. Please try again.", "csrf_token": csrf_token_new
        })

    if not check_rate_limit(client_ip):
        csrf_token_new = generate_csrf_token()
        return templates.TemplateResponse("login.html", {
            "request": request, "error": "Too many login attempts. Please try again in 15 minutes.", "csrf_token": csrf_token_new
        })

    user = authenticate_user(db, username, password)
    if user:
        if client_ip in login_attempts:
            del login_attempts[client_ip]
        session_token = create_session(username)
        response = RedirectResponse(url="/dashboard", status_code=302)
        response.set_cookie(
            key="session_token", value=session_token,
            httponly=True, secure=IS_PRODUCTION,
            samesite="lax",
            max_age=86400
        )
        return response
    else:
        record_login_attempt(client_ip)
        csrf_token_new = generate_csrf_token()
        return templates.TemplateResponse("login.html", {
            "request": request, "error": "Invalid username or password", "csrf_token": csrf_token_new
        })


# Keep /index for backwards compat
@app.get("/index", response_class=HTMLResponse)
async def index_redirect(request: Request):
    return RedirectResponse(url="/dashboard", status_code=302)


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request):
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    return templates.TemplateResponse("dashboard.html", {"request": request, "username": user})


@app.post("/logout")
async def logout(request: Request):
    session_token = request.cookies.get("session_token")
    if session_token:
        _delete_session(session_token)
    response = RedirectResponse(url="/login", status_code=302)
    response.delete_cookie("session_token")
    return response


# --- WebSocket ---

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    # Check session auth from cookie (DB-backed)
    from database import SessionToken
    session_token = websocket.cookies.get("session_token")
    if not session_token:
        await websocket.close(code=4001)
        return
    db = SessionLocal()
    try:
        s = db.query(SessionToken).filter(SessionToken.token == session_token).first()
        if not s or time.time() - s.created_at > SESSION_MAX_AGE:
            await websocket.close(code=4001)
            return
    finally:
        db.close()

    await manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)


# --- REST API (all require authentication) ---

def _require_auth(request: Request):
    """Return user or raise 401."""
    user = get_current_user(request)
    if not user:
        return None
    return user


def _require_auth_simple(request: Request) -> bool:
    """Simple boolean check for authentication."""
    user = get_current_user(request)
    return user is not None


def _detect_attack_patterns(request: Request) -> bool:
    """Detect common attack patterns in requests."""
    import re

    request_str = str(request.url).lower()
    suspicious_patterns = [
        r"union.*select",     # SQL injection attempts
        r"<script.*>",        # XSS attempts
        r"\.\.\/",            # Directory traversal
        r"eval\(",            # Code injection
        r"exec\(",            # Command injection
        r"system\(",          # System command injection
        r"phpinfo\(",         # PHP info disclosure
        r"/etc/passwd",       # Linux system file access
        r"/proc/self",        # Process information access
        r"javascript:",       # XSS via javascript protocol
        r"data:.*base64",     # Malicious data URIs
    ]

    for pattern in suspicious_patterns:
        if re.search(pattern, request_str, re.IGNORECASE):
            return True

    return False


@app.get("/api/news")
@limiter.limit("60/minute")
async def api_news(request: Request):
    if not _require_auth(request):
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    from collectors.news import articles_cache
    return JSONResponse(articles_cache[-100:])


@app.get("/api/markets")
@limiter.limit("60/minute")
async def api_markets(request: Request):
    if not _require_auth(request):
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    from collectors.markets import market_cache
    return JSONResponse({
        "forex": market_cache.get("forex", {}),
        "stocks": market_cache.get("stocks", {}),
        "crypto": market_cache.get("crypto", {}),
        "fear_greed": market_cache.get("fear_greed", {}),
        "intraday": market_cache.get("intraday", {}),
    })


@app.get("/api/military")
@limiter.limit("60/minute")
async def api_military(request: Request):
    if not _require_auth(request):
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    from collectors.military import assets_cache
    return JSONResponse(assets_cache)


@app.get("/api/cyber")
@limiter.limit("60/minute")
async def api_cyber(request: Request):
    if not _require_auth(request):
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    from collectors.cyber import cyber_cache, stats_cache
    return JSONResponse({"events": cyber_cache, "stats": stats_cache})


@app.get("/api/polymarket")
@limiter.limit("60/minute")
async def api_polymarket(request: Request):
    if not _require_auth(request):
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    from collectors.polymarket import polymarket_cache
    return JSONResponse(polymarket_cache)


@app.get("/api/pizzint")
@limiter.limit("60/minute")
async def api_pizzint(request: Request):
    if not _require_auth(request):
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    from collectors.pizzint import pizzint_cache
    return JSONResponse(pizzint_cache)


@app.get("/api/ships")
@limiter.limit("60/minute")
async def api_ships(request: Request, filter: str = "china", country: str = ""):
    if not _require_auth(request):
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    from collectors.ships import get_ships_list
    if filter not in ("all", "china", "known", "moving", "notable"):
        filter = "china"
    return JSONResponse(get_ships_list(filter_mode=filter, country=country))


@app.get("/api/threats")
@limiter.limit("60/minute")
async def api_threats(request: Request):
    if not _require_auth(request):
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    from collectors.news import articles_cache
    from collectors.military import assets_cache
    from collectors.cyber import cyber_cache
    from scoring import compute_region_scores
    scores = compute_region_scores(articles_cache, assets_cache, cyber_cache)
    return JSONResponse(scores)


@app.get("/api/threats/feed")
@limiter.limit("60/minute")
async def api_threats_feed(request: Request):
    if not _require_auth(request):
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    from threat_engine import get_feed
    return JSONResponse(get_feed())


@app.get("/api/threats/stats")
@limiter.limit("60/minute")
async def api_threats_stats(request: Request):
    if not _require_auth(request):
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    from threat_engine import get_stats
    return JSONResponse(get_stats())


@app.get("/api/threats/config")
@limiter.limit("30/minute")
async def api_threats_config_get(request: Request):
    if not _require_auth(request):
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    from threat_engine import load_config
    return JSONResponse(load_config())


@app.post("/api/threats/config")
@limiter.limit("10/minute")
async def api_threats_config_post(request: Request):
    if not _require_auth(request):
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    from threat_engine import save_config
    body = await request.json()

    # Validate config schema
    ALLOWED_KEYS = {"keyword_rules", "llm_threshold", "notify_threshold", "llm_enabled", "llm_prompt", "cooldown_minutes", "sources"}
    if not isinstance(body, dict) or not set(body.keys()).issubset(ALLOWED_KEYS):
        return JSONResponse({"error": "Invalid config keys"}, status_code=400)
    if "keyword_rules" in body:
        if not isinstance(body["keyword_rules"], dict):
            return JSONResponse({"error": "keyword_rules must be a dict"}, status_code=400)
        for k, v in body["keyword_rules"].items():
            if not isinstance(k, str) or not isinstance(v, (int, float)) or not (0 <= v <= 10):
                return JSONResponse({"error": f"Invalid keyword rule: {k}"}, status_code=400)
    if "llm_threshold" in body and not (isinstance(body["llm_threshold"], (int, float)) and 1 <= body["llm_threshold"] <= 15):
        return JSONResponse({"error": "llm_threshold must be 1-15"}, status_code=400)
    if "notify_threshold" in body and not (isinstance(body["notify_threshold"], (int, float)) and 1 <= body["notify_threshold"] <= 10):
        return JSONResponse({"error": "notify_threshold must be 1-10"}, status_code=400)
    if "cooldown_minutes" in body and not (isinstance(body["cooldown_minutes"], (int, float)) and 1 <= body["cooldown_minutes"] <= 120):
        return JSONResponse({"error": "cooldown_minutes must be 1-120"}, status_code=400)
    if "llm_enabled" in body and not isinstance(body["llm_enabled"], bool):
        return JSONResponse({"error": "llm_enabled must be boolean"}, status_code=400)
    if "llm_prompt" in body and (not isinstance(body["llm_prompt"], str) or len(body["llm_prompt"]) > 2000):
        return JSONResponse({"error": "llm_prompt must be string under 2000 chars"}, status_code=400)
    if "sources" in body:
        if not isinstance(body["sources"], dict):
            return JSONResponse({"error": "sources must be a dict"}, status_code=400)
        for k, v in body["sources"].items():
            if not isinstance(v, bool):
                return JSONResponse({"error": f"sources.{k} must be boolean"}, status_code=400)

    try:
        save_config(body)
        return JSONResponse({"status": "ok"})
    except Exception as e:
        logger.error(f"[API] Failed to save threat config: {e}")
        return JSONResponse({"error": f"Failed to save config: {str(e)}"}, status_code=500)


# --- Background tasks ---

@app.on_event("startup")
async def start_collectors():
    from collectors.news import NewsCollector
    from collectors.markets import MarketsCollector
    from collectors.military import MilitaryCollector
    from collectors.cyber import CyberCollector
    from collectors.pizzint import PizzIntCollector
    from collectors.polymarket import PolymarketCollector
    from collectors.ships import ShipCollector

    news = NewsCollector()
    news.set_db(SessionLocal)
    cyber = CyberCollector()
    cyber.set_db(SessionLocal)

    asyncio.create_task(news.run())
    asyncio.create_task(MarketsCollector().run())
    asyncio.create_task(MilitaryCollector().run())
    asyncio.create_task(cyber.run())
    asyncio.create_task(PizzIntCollector().run())
    asyncio.create_task(PolymarketCollector().run())
    asyncio.create_task(ShipCollector().run())

    # Periodic session cleanup
    async def _session_cleanup_loop():
        while True:
            await asyncio.sleep(300)  # every 5 min
            _cleanup_expired_sessions()
    asyncio.create_task(_session_cleanup_loop())

    logger.info("All collectors started")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
