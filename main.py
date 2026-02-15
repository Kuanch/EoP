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

# Logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

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

# Security headers middleware
@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
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

# Session storage with expiration
SESSION_MAX_AGE = 3600  # 1 hour
sessions: dict[str, dict] = {}  # token -> {"username": str, "created": float}

# Login attempt tracking
login_attempts = {}


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


def check_rate_limit(ip: str, max_attempts: int = 5, window_minutes: int = 15) -> bool:
    now = datetime.now()
    cutoff_time = now - timedelta(minutes=window_minutes)
    if ip in login_attempts:
        login_attempts[ip] = [t for t in login_attempts[ip] if t > cutoff_time]
    else:
        login_attempts[ip] = []
    return len(login_attempts[ip]) < max_attempts


def record_login_attempt(ip: str):
    if ip not in login_attempts:
        login_attempts[ip] = []
    login_attempts[ip].append(datetime.now())


def create_session(username: str) -> str:
    session_token = secrets.token_urlsafe(32)
    sessions[session_token] = {"username": username, "created": time.time()}
    return session_token


def get_current_user(request: Request) -> Optional[str]:
    session_token = request.cookies.get("session_token")
    if session_token and session_token in sessions:
        session = sessions[session_token]
        # Check expiration
        if time.time() - session["created"] > SESSION_MAX_AGE:
            del sessions[session_token]
            return None
        return session["username"]
    return None


def _cleanup_expired_sessions():
    """Remove expired sessions to prevent memory leak."""
    now = time.time()
    expired = [t for t, s in sessions.items() if now - s["created"] > SESSION_MAX_AGE]
    for t in expired:
        del sessions[t]


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
            samesite="strict" if IS_PRODUCTION else "lax",
            max_age=3600
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


@app.get("/logout")
async def logout(request: Request):
    session_token = request.cookies.get("session_token")
    if session_token and session_token in sessions:
        del sessions[session_token]
    response = RedirectResponse(url="/login", status_code=302)
    response.delete_cookie("session_token")
    return response


# --- WebSocket ---

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    # Check session auth from cookie
    session_token = websocket.cookies.get("session_token")
    if not session_token or session_token not in sessions:
        await websocket.close(code=4001)
        return
    # Verify session not expired
    session = sessions[session_token]
    if time.time() - session["created"] > SESSION_MAX_AGE:
        del sessions[session_token]
        await websocket.close(code=4001)
        return

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
