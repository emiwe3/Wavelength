import os
import httpx
from fastapi import FastAPI, Request, Form
from fastapi.responses import JSONResponse, RedirectResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from dotenv import load_dotenv
from db import init_db, upsert_user, get_user, add_slack_workspace, get_slack_workspaces

load_dotenv()

app = FastAPI()
app.add_middleware(SessionMiddleware, secret_key=os.getenv("SECRET_KEY", "dev-secret-change-me"))
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:9000", "http://localhost:5174", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_URL = os.getenv("APP_BASE_URL", "http://localhost:8000")
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:9000")

GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
GOOGLE_REDIRECT_URI = f"{BASE_URL}/auth/google/callback"

GMAIL_SCOPE = "https://www.googleapis.com/auth/gmail.readonly"
CALENDAR_SCOPE = "https://www.googleapis.com/auth/calendar.events"

SLACK_CLIENT_ID = os.getenv("SLACK_CLIENT_ID")
SLACK_CLIENT_SECRET = os.getenv("SLACK_CLIENT_SECRET")
SLACK_REDIRECT_URI = f"{BASE_URL}/auth/slack/callback"
SLACK_SCOPES = "channels:history,im:history,channels:read,im:read"

CANVAS_CLIENT_ID = os.getenv("CANVAS_CLIENT_ID")
CANVAS_CLIENT_SECRET = os.getenv("CANVAS_CLIENT_SECRET")


@app.on_event("startup")
def startup():
    init_db()


@app.post("/api/register")
async def register(request: Request):
    data = await request.json()
    phone = data.get("phone", "").strip()
    if not phone:
        return JSONResponse({"error": "Phone number required"}, status_code=400)
    upsert_user(phone)
    request.session["phone"] = phone
    return {"ok": True, "phone": phone}


@app.get("/api/config")
async def config():
    canvas_base = os.getenv("CANVAS_BASE_URL", "").strip().rstrip("/")
    domain = canvas_base.replace("https://", "").replace("http://", "") if canvas_base else ""
    return {"canvas_domain": domain}


@app.post("/api/logout")
async def logout(request: Request):
    request.session.clear()
    return {"ok": True}


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
        "slack_workspaces": get_slack_workspaces(phone),
    }


@app.get("/auth/google/start")
async def google_start(request: Request, phone: str = None):
    phone = phone or request.session.get("phone")
    if not phone:
        return RedirectResponse(f"{FRONTEND_URL}?error=no_phone")
    scopes = ["openid", "email", GMAIL_SCOPE, CALENDAR_SCOPE]
    params = {
        "client_id": GOOGLE_CLIENT_ID,
        "redirect_uri": GOOGLE_REDIRECT_URI,
        "response_type": "code",
        "scope": " ".join(scopes),
        "access_type": "offline",
        "prompt": "consent",
        "state": phone,
    }
    from urllib.parse import urlencode
    return RedirectResponse(f"https://accounts.google.com/o/oauth2/v2/auth?{urlencode(params)}")


@app.get("/auth/google/callback")
async def google_callback(request: Request, code: str = None, state: str = None, error: str = None):
    if error or not code:
        return RedirectResponse(f"{FRONTEND_URL}?error=google_{error or 'cancelled'}")
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
    gmail_credentials = {
        "token": tokens.get("access_token"),
        "refresh_token": tokens.get("refresh_token"),
        "token_uri": "https://oauth2.googleapis.com/token",
        "client_id": GOOGLE_CLIENT_ID,
        "client_secret": GOOGLE_CLIENT_SECRET,
        "scopes": [GMAIL_SCOPE, CALENDAR_SCOPE],
    }
    upsert_user(phone, gmail_credentials=gmail_credentials)
    request.session["phone"] = phone
    return RedirectResponse(f"{FRONTEND_URL}?connected=google")


@app.post("/api/ical")
async def save_ical(request: Request):
    data = await request.json()
    phone = request.session.get("phone")
    if not phone:
        return JSONResponse({"error": "Not registered"}, status_code=401)
    ical_url = data.get("ical_url", "").strip()
    if not ical_url:
        return JSONResponse({"error": "iCal URL required"}, status_code=400)

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


@app.post("/api/canvas/token")
async def canvas_token(request: Request):
    data = await request.json()
    phone = data.get("phone") or request.session.get("phone")
    if not phone:
        return JSONResponse({"error": "Not registered"}, status_code=401)
    token = data.get("token", "").strip()
    domain = data.get("domain", "").strip().rstrip("/")
    if not token or not domain:
        return JSONResponse({"error": "Token and domain required"}, status_code=400)

    async with httpx.AsyncClient(follow_redirects=True) as client:
        resp = await client.get(
            f"https://{domain}/api/v1/users/self",
            headers={"Authorization": f"Bearer {token}"},
        )
    if resp.status_code != 200:
        return JSONResponse({"error": "Invalid Canvas token or domain"}, status_code=400)

    upsert_user(phone, canvas_token=token, canvas_domain=domain)
    return {"ok": True}


@app.get("/auth/canvas/start")
async def canvas_oauth_start(request: Request, domain: str):
    phone = request.session.get("phone")
    if not phone:
        return RedirectResponse(f"{FRONTEND_URL}?error=no_phone")
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
        return RedirectResponse(f"{FRONTEND_URL}?error=canvas_{error or 'cancelled'}")
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
    return RedirectResponse(f"{FRONTEND_URL}?connected=canvas")


@app.get("/auth/slack/start")
async def slack_start(request: Request, phone: str = None):
    phone = phone or request.session.get("phone")
    if not phone:
        return RedirectResponse(f"{FRONTEND_URL}?error=no_phone")
    from urllib.parse import urlencode
    return RedirectResponse(
        f"https://slack.com/oauth/v2/authorize?"
        + urlencode({
            "client_id": SLACK_CLIENT_ID,
            "user_scope": SLACK_SCOPES,
            "redirect_uri": SLACK_REDIRECT_URI,
            "state": phone,
        })
    )


@app.get("/auth/slack/callback")
async def slack_callback(request: Request, code: str = None, state: str = None, error: str = None):
    if error or not code:
        return RedirectResponse(f"{FRONTEND_URL}?error=slack_{error or 'cancelled'}")
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
    team_id = data.get("team", {}).get("id", "")
    team_name = data.get("team", {}).get("name", "Unknown Workspace")
    if user_token and team_id:
        add_slack_workspace(phone, user_token, team_id, team_name)
    upsert_user(phone, slack_token=user_token)
    request.session["phone"] = phone
    return RedirectResponse(f"{FRONTEND_URL}?connected=slack")


_recent: dict = {}

@app.post("/api/bot/message")
async def bot_message(request: Request):
    import time
    import agent as agent_mod
    data = await request.json()
    phone = data.get("phone", "").strip()
    text = data.get("text", "").strip()
    image_base64 = data.get("image_base64")
    image_media_type = data.get("image_media_type")
    audio_path = data.get("audio_path")
    if not phone or (not text and not image_base64 and not audio_path):
        return JSONResponse({"error": "phone and text, image, or audio required"}, status_code=400)

    key = (phone, text)
    now = time.time()
    if now - _recent.get(key, 0) < 5:
        return JSONResponse({"reply": None})
    _recent[key] = now

    user = get_user(phone)
    if not user:
        # Try normalized lookup: strip non-digits, add +1 prefix for US numbers
        digits = "".join(c for c in phone if c.isdigit())
        normalized = f"+1{digits[-10:]}" if len(digits) >= 10 else phone
        if normalized != phone:
            user = get_user(normalized)
        if not user:
            print(f"⚠️  New user from {phone} (normalized: {normalized}) — no credentials")
            upsert_user(phone)
            user = get_user(phone)
        else:
            print(f"ℹ️  Matched {phone} → {normalized}")
            phone = normalized
    print(f"📋 User {phone}: gmail={bool(user.get('gmail_credentials'))}, canvas={bool(user.get('canvas_token'))}, slack={bool(user.get('slack_token'))}, ical={bool(user.get('ical_url'))}")
    try:
        reply, actions = agent_mod.reply(user, text, image_base64=image_base64, image_media_type=image_media_type, audio_path=audio_path)
    except Exception as exc:
        reply, actions = f"Sorry, something went wrong: {exc}", {}
    return JSONResponse({"reply": reply, **actions})


# ── Location (from Photon Find My) ──────────────────────────────────────────

@app.post("/api/location")
async def update_location(request: Request):
    data = await request.json()
    phone = data.get("phone", "").strip()
    lat = data.get("lat")
    lng = data.get("lng")
    if not phone or lat is None or lng is None:
        return JSONResponse({"error": "phone, lat, lng required"}, status_code=400)
    upsert_user(phone, current_lat=lat, current_lng=lng)
    return {"ok": True}


@app.post("/api/location/link")
async def link_findmy(request: Request):
    data = await request.json()
    phone = data.get("phone", "").strip()
    findmy_id = data.get("findmy_id", "").strip()
    findmy_name = data.get("findmy_name", "").strip()
    if not phone or (not findmy_id and not findmy_name):
        return JSONResponse({"error": "phone and findmy_id or findmy_name required"}, status_code=400)
    kwargs = {}
    if findmy_id:
        kwargs["findmy_id"] = findmy_id
    if findmy_name:
        kwargs["findmy_name"] = findmy_name
    upsert_user(phone, **kwargs)
    return {"ok": True}


@app.post("/api/location/findmy")
async def update_location_findmy(request: Request):
    data = await request.json()
    findmy_id = data.get("findmy_id", "")
    name = data.get("name", "")
    lat = data.get("lat")
    lng = data.get("lng")
    if lat is None or lng is None:
        return JSONResponse({"error": "lat and lng required"}, status_code=400)

    from db import _connect
    with _connect() as conn:
        row = conn.execute(
            "SELECT phone FROM users WHERE findmy_id = ?", (findmy_id,)
        ).fetchone()
        if not row and name:
            row = conn.execute(
                "SELECT phone FROM users WHERE findmy_name = ?", (name,)
            ).fetchone()
    if not row:
        return JSONResponse({"error": "no matching user"}, status_code=404)

    upsert_user(row["phone"], current_lat=lat, current_lng=lng)
    return {"ok": True, "phone": row["phone"]}


# Serve frontend build — must be last so API routes take priority
_frontend = os.path.join(os.path.dirname(__file__), "../frontend/dist")
if os.path.isdir(_frontend):
    app.mount("/assets", StaticFiles(directory=os.path.join(_frontend, "assets")), name="assets")

    @app.get("/{full_path:path}")
    async def serve_frontend(full_path: str):
        return FileResponse(os.path.join(_frontend, "index.html"))
