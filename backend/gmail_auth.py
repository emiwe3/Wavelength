"""
gmail_auth.py — one-shot Gmail OAuth flow.
Opens browser, captures callback, saves credentials to DB.
Run: python3 gmail_auth.py <phone_number>
"""

import json
import os
import sys
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

import httpx
from dotenv import load_dotenv

load_dotenv()

CLIENT_ID = os.environ["GOOGLE_CLIENT_ID"].strip()
CLIENT_SECRET = os.environ["GOOGLE_CLIENT_SECRET"].strip()
REDIRECT_URI = "http://localhost:8000/auth/google/callback"
SCOPE = " ".join([
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/calendar.events",
])

auth_code = None


class CallbackHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        global auth_code
        parsed = urlparse(self.path)
        if parsed.path != "/auth/google/callback":
            self.send_response(404)
            self.end_headers()
            return
        params = parse_qs(parsed.query)
        auth_code = params.get("code", [None])[0]
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"<h2>Done! You can close this tab.</h2>")

    def log_message(self, *args):
        pass


def get_auth_url() -> str:
    import urllib.parse
    params = {
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "scope": SCOPE,
        "access_type": "offline",
        "prompt": "consent",
    }
    return "https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode(params)


def exchange_code(code: str) -> dict:
    resp = httpx.post("https://oauth2.googleapis.com/token", data={
        "code": code,
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "redirect_uri": REDIRECT_URI,
        "grant_type": "authorization_code",
    })
    resp.raise_for_status()
    data = resp.json()
    return {
        "token": data["access_token"],
        "refresh_token": data.get("refresh_token"),
        "token_uri": "https://oauth2.googleapis.com/token",
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "scopes": SCOPE.split(),
    }


if __name__ == "__main__":
    phone = sys.argv[1] if len(sys.argv) > 1 else "+15550001234"

    url = get_auth_url()
    print(f"Opening browser for Gmail OAuth...")
    print(f"URL: {url}\n")
    webbrowser.open(url)

    print("Waiting for OAuth callback on localhost:8000...")
    server = HTTPServer(("localhost", 8000), CallbackHandler)
    server.handle_request()

    if not auth_code:
        print("❌ No code received.")
        sys.exit(1)

    print("Exchanging code for credentials...")
    creds = exchange_code(auth_code)

    import db
    db.init_db()
    db.upsert_user(phone, gmail_credentials=creds)
    print(f"✅ Gmail credentials saved for {phone}")
    print("Run python3 test_all.py to test.")
