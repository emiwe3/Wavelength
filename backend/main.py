import os
import httpx
from fastapi import FastAPI, Request, Form
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware
from dotenv import load_dotenv
from db import init_db, upsert_user, get_user

load_dotenv()

app = FastAPI()
app.add_middleware(SessionMiddleware, secret_key=os.getenv("SECRET_KEY", "dev-secret-change-me"))
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:5174"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_URL = os.getenv("APP_BASE_URL", "http://localhost:8000")

GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
GOOGLE_REDIRECT_URI = f"{BASE_URL}/auth/google/callback"

# Only Gmail scope — Calendar uses the iCal URL, no OAuth needed
GMAIL_SCOPE = "https://www.googleapis.com/auth/gmail.readonly"

SLACK_CLIENT_ID = os.getenv("SLACK_CLIENT_ID")
SLACK_CLIENT_SECRET = os.getenv("SLACK_CLIENT_SECRET")
SLACK_REDIRECT_URI = f"{BASE_URL}/auth/slack/callback"
SLACK_SCOPES = "channels:history,im:history,channels:read,im:read"

CANVAS_CLIENT_ID = os.getenv("CANVAS_CLIENT_ID")
CANVAS_CLIENT_SECRET = os.getenv("CANVAS_CLIENT_SECRET")


@app.on_event("startup")
def startup():
    init_db()


# ── Phone registration ──────────────────────────────────────────────────────

@app.post("/api/register")
async def register(request: Request):
    data = await request.json()
    phone = data.get("phone", "").strip()
    if not phone:
        return JSONResponse({"error": "Phone number required"}, status_code=400)
    upsert_user(phone)
    request.session["phone"] = phone
    return {"ok": True, "phone": phone}


@app.get("/api/status")
async def status(request: Request):
    phone = request.session.get("phone")
    if not phone:
        return {"phone": None, "google": False, "ical": False, "canvas": False, "slack": False}
    user = get_user(phone)
    if not user:
        return {"phone": phone, "google": False, "ical": False, "canvas": False, "slack": False}
    return {
        "phone": phone,
        "google": bool(user.get("gmail_credentials")),
        "ical": bool(user.get("ical_url")),
        "canvas": bool(user.get("canvas_token")),
        "slack": bool(user.get("slack_token")),
    }


# ── Google OAuth (Gmail only) ───────────────────────────────────────────────

@app.get("/auth/google/start")
async def google_start(request: Request):
    phone = request.session.get("phone")
    if not phone:
        return RedirectResponse("http://localhost:5173?error=no_phone")
    scopes = ["openid", "email", GMAIL_SCOPE]
    params = {
        "client_id": GOOGLE_CLIENT_ID,
        "redirect_uri": GOOGLE_REDIRECT_URI,
        "response_type": "code",
        "scope": " ".join(scopes),
        "access_type": "offline",
        "prompt": "consent",
        "state": phone,
    }
    query = "&".join(f"{k}={v}" for k, v in params.items())
    return RedirectResponse(f"https://accounts.google.com/o/oauth2/v2/auth?{query}")


@app.get("/auth/google/callback")
async def google_callback(request: Request, code: str = None, state: str = None, error: str = None):
    if error or not code:
        return RedirectResponse(f"http://localhost:5173?error=google_{error or 'cancelled'}")
    phone = state or request.session.get("phone")
    async with httpx.AsyncClient() as client:
        resp = await client.post("https://oauth2.googleapis.com/token", data={
            "code": code,
            "client_id": GOOGLE_CLIENT_ID,
            "client_secret": GOOGLE_CLIENT_SECRET,
            "redirect_uri": GOOGLE_REDIRECT_URI,
            "grant_type": "authorization_code",
        })
    tokens = resp.json()
    # Store in the format expected by gmail.py / google-auth library
    gmail_credentials = {
        "token": tokens.get("access_token"),
        "refresh_token": tokens.get("refresh_token"),
        "token_uri": "https://oauth2.googleapis.com/token",
        "client_id": GOOGLE_CLIENT_ID,
        "client_secret": GOOGLE_CLIENT_SECRET,
        "scopes": [GMAIL_SCOPE],
    }
    upsert_user(phone, gmail_credentials=gmail_credentials)
    request.session["phone"] = phone
    return RedirectResponse("http://localhost:5173?connected=google")


# ── Google Calendar iCal URL ────────────────────────────────────────────────

@app.post("/api/ical")
async def save_ical(request: Request):
    data = await request.json()
    phone = request.session.get("phone")
    if not phone:
        return JSONResponse({"error": "Not registered"}, status_code=401)
    ical_url = data.get("ical_url", "").strip()
    if not ical_url:
        return JSONResponse({"error": "iCal URL required"}, status_code=400)

    # Validate the URL is reachable and parses as iCal
    try:
        import urllib.request
        with urllib.request.urlopen(ical_url, timeout=10) as resp:
            content = resp.read(512)
        if b"BEGIN:VCALENDAR" not in content:
            return JSONResponse({"error": "URL does not appear to be a valid iCal feed"}, status_code=400)
    except Exception as exc:
        return JSONResponse({"error": f"Could not fetch iCal URL: {exc}"}, status_code=400)

    upsert_user(phone, ical_url=ical_url)
    return {"ok": True}


# ── Canvas ──────────────────────────────────────────────────────────────────

@app.post("/api/canvas/token")
async def canvas_token(request: Request):
    data = await request.json()
    phone = request.session.get("phone")
    if not phone:
        return JSONResponse({"error": "Not registered"}, status_code=401)
    token = data.get("token", "").strip()
    domain = data.get("domain", "").strip().rstrip("/")
    if not token or not domain:
        return JSONResponse({"error": "Token and domain required"}, status_code=400)

    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"https://{domain}/api/v1/users/self",
            headers={"Authorization": f"Bearer {token}"},
        )
    if resp.status_code != 200:
        return JSONResponse({"error": "Invalid Canvas token or domain"}, status_code=400)

    upsert_user(phone, canvas_token=token)
    return {"ok": True}


# Canvas OAuth (only works if your school has issued you a developer key)
@app.get("/auth/canvas/start")
async def canvas_oauth_start(request: Request, domain: str):
    phone = request.session.get("phone")
    if not phone:
        return RedirectResponse("http://localhost:5173?error=no_phone")
    redirect_uri = f"{BASE_URL}/auth/canvas/callback"
    return RedirectResponse(
        f"https://{domain}/login/oauth2/auth"
        f"?client_id={CANVAS_CLIENT_ID}"
        f"&redirect_uri={redirect_uri}"
        f"&response_type=code"
        f"&state={phone}|{domain}"
    )


@app.get("/auth/canvas/callback")
async def canvas_oauth_callback(request: Request, code: str = None, state: str = None, error: str = None):
    if error or not code:
        return RedirectResponse(f"http://localhost:5173?error=canvas_{error or 'cancelled'}")
    phone, domain = state.split("|")
    redirect_uri = f"{BASE_URL}/auth/canvas/callback"
    async with httpx.AsyncClient() as client:
        resp = await client.post(f"https://{domain}/login/oauth2/token", data={
            "code": code,
            "client_id": CANVAS_CLIENT_ID,
            "client_secret": CANVAS_CLIENT_SECRET,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        })
    tokens = resp.json()
    upsert_user(phone, canvas_token=tokens.get("access_token"))
    request.session["phone"] = phone
    return RedirectResponse("http://localhost:5173?connected=canvas")


# ── Slack OAuth ─────────────────────────────────────────────────────────────

@app.get("/auth/slack/start")
async def slack_start(request: Request):
    phone = request.session.get("phone")
    if not phone:
        return RedirectResponse("http://localhost:5173?error=no_phone")
    return RedirectResponse(
        f"https://slack.com/oauth/v2/authorize"
        f"?client_id={SLACK_CLIENT_ID}"
        f"&user_scope={SLACK_SCOPES}"
        f"&redirect_uri={SLACK_REDIRECT_URI}"
        f"&state={phone}"
    )


@app.get("/auth/slack/callback")
async def slack_callback(request: Request, code: str = None, state: str = None, error: str = None):
    if error or not code:
        return RedirectResponse(f"http://localhost:5173?error=slack_{error or 'cancelled'}")
    phone = state or request.session.get("phone")
    async with httpx.AsyncClient() as client:
        resp = await client.post("https://slack.com/api/oauth.v2.access", data={
            "code": code,
            "client_id": SLACK_CLIENT_ID,
            "client_secret": SLACK_CLIENT_SECRET,
            "redirect_uri": SLACK_REDIRECT_URI,
        })
    data = resp.json()
    user_token = data.get("authed_user", {}).get("access_token")
    upsert_user(phone, slack_token=user_token)
    request.session["phone"] = phone
    return RedirectResponse("http://localhost:5173?connected=slack")