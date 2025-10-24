from fastapi import FastAPI, Request, Form, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
import secrets

app = FastAPI()

# Templates
templates = Jinja2Templates(directory="templates")

# Simple session storage (in production, use Redis or database)
sessions = {}

# Hardcoded credentials
ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "password"


def create_session(username: str) -> str:
    """Create a session token for a user"""
    session_token = secrets.token_urlsafe(32)
    sessions[session_token] = username
    return session_token


def get_current_user(request: Request) -> str | None:
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

    return templates.TemplateResponse("login.html", {"request": request})


@app.post("/login")
async def login(request: Request, username: str = Form(...), password: str = Form(...)):
    """Handle login form submission"""
    if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
        # Create session
        session_token = create_session(username)

        # Redirect to index with session cookie
        response = RedirectResponse(url="/index", status_code=302)
        response.set_cookie(
            key="session_token",
            value=session_token,
            httponly=True,
            max_age=3600,  # 1 hour
            samesite="lax"
        )
        return response
    else:
        # Invalid credentials
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "error": "Invalid username or password"}
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
