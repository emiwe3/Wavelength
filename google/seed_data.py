"""
seed_data.py — one-time script to populate the test Google account with
realistic dummy emails and calendar events for PulsePoint development.

Run once:
    pip3 install -r requirements.txt
    python3 seed_data.py

It will open a browser for Google OAuth. Credentials are saved to
seed_token.json so you won't need to re-auth on subsequent runs.
"""

import base64
import os
import threading
import webbrowser
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from email.utils import formatdate
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from dotenv import load_dotenv
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build

load_dotenv(os.path.join(os.path.dirname(__file__), "..", "backend", ".env"))

SCOPES = [
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/calendar",
]

REDIRECT_URI = "http://localhost:8000/auth/google/callback"
TOKEN_FILE = Path("seed_token.json")
STUDENT_EMAIL = "clarkkenthp2026@gmail.com"
TZ = "America/New_York"

# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

class _CallbackHandler(BaseHTTPRequestHandler):
    """Minimal HTTP handler that captures the OAuth code from the callback."""
    code = None  # type: str

    def do_GET(self):
        if urlparse(self.path).path == "/auth/google/callback":
            _CallbackHandler.code = parse_qs(urlparse(self.path).query).get("code", [None])[0]
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"Auth complete! You can close this tab.")
            # Shut down the server from a separate thread to avoid deadlock
            threading.Thread(target=self.server.shutdown).start()

    def log_message(self, *args):
        pass  # silence request logs


def get_credentials() -> Credentials:
    # Delete stale token file that has no refresh token
    if TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
        if creds.valid:
            return creds
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            TOKEN_FILE.write_text(creds.to_json())
            return creds
        TOKEN_FILE.unlink()  # stale — delete and re-auth

    flow = Flow.from_client_config(
        {
            "web": {
                "client_id": os.environ["GOOGLE_CLIENT_ID"],
                "client_secret": os.environ["GOOGLE_CLIENT_SECRET"],
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": [REDIRECT_URI],
            }
        },
        scopes=SCOPES,
        redirect_uri=REDIRECT_URI,
    )

    url, _ = flow.authorization_url(access_type="offline", prompt="consent")

    # serve_forever handles multiple requests (browser prefetches etc.)
    # and shuts down automatically once we receive the code
    server = HTTPServer(("localhost", 8000), _CallbackHandler)
    thread = threading.Thread(target=server.serve_forever)
    thread.daemon = True
    thread.start()

    print("Opening browser for Google auth...")
    webbrowser.open(url)
    thread.join(timeout=300)  # 5 minutes

    if not _CallbackHandler.code:
        raise RuntimeError("No auth code received — did the browser open?")

    flow.fetch_token(code=_CallbackHandler.code)
    TOKEN_FILE.write_text(flow.credentials.to_json())
    return flow.credentials


# ---------------------------------------------------------------------------
# Email helpers
# ---------------------------------------------------------------------------

def _raw_message(from_addr: str, subject: str, body: str, days_ago: float = 0) -> str:
    """Build a base64url-encoded RFC 2822 message."""
    msg = MIMEText(body)
    msg["From"] = from_addr
    msg["To"] = STUDENT_EMAIL
    msg["Subject"] = subject
    # Backdate so emails look like they arrived recently
    sent_at = datetime.now() - timedelta(days=days_ago)
    msg["Date"] = formatdate(sent_at.timestamp(), localtime=True)
    return base64.urlsafe_b64encode(msg.as_bytes()).decode()


def insert_email(gmail, from_addr: str, subject: str, body: str, days_ago: float = 0):
    gmail.users().messages().insert(
        userId="me",
        body={
            "raw": _raw_message(from_addr, subject, body, days_ago),
            "labelIds": ["INBOX", "UNREAD"],
        },
    ).execute()
    print(f"  [email] {subject}")


# ---------------------------------------------------------------------------
# Calendar helpers
# ---------------------------------------------------------------------------

def _dt(base: datetime, hour: int, minute: int = 0) -> str:
    """Return an ISO 8601 string for `base` date at the given local time."""
    return base.replace(hour=hour, minute=minute, second=0, microsecond=0).isoformat()


def create_event(
    cal,
    summary: str,
    start_iso: str,
    end_iso: str,
    description: str = "",
    location: str = "",
):
    cal.events().insert(
        calendarId="primary",
        body={
            "summary": summary,
            "description": description,
            "location": location,
            "start": {"dateTime": start_iso, "timeZone": TZ},
            "end": {"dateTime": end_iso, "timeZone": TZ},
        },
    ).execute()
    print(f"  [event] {summary}  ({start_iso[:16]})")


# ---------------------------------------------------------------------------
# Seed data
# ---------------------------------------------------------------------------

def seed_emails(gmail):
    print("\nInserting emails...")

    insert_email(
        gmail,
        from_addr="Prof. Daniel Hartman <d.hartman@cs.university.edu>",
        subject="CS 301 — Problem Set 4 due Thursday at 11:59pm",
        body=(
            "Hi everyone,\n\n"
            "Just a reminder that Problem Set 4 is due this Thursday at 11:59pm on Gradescope. "
            "It covers dynamic programming and graph traversal (lectures 12–15).\n\n"
            "I've posted two extra practice problems on Canvas if you'd like more prep. "
            "Office hours this Wednesday 3–4pm in Gates 210 if you have questions.\n\n"
            "— Prof. Hartman"
        ),
        days_ago=0.3,
    )

    insert_email(
        gmail,
        from_addr="Registrar's Office <registrar@university.edu>",
        subject="Spring Add/Drop Deadline Reminder — This Friday at 5pm",
        body=(
            "Dear student,\n\n"
            "This is a reminder that the Spring semester Add/Drop deadline is this Friday at 5:00pm. "
            "After this date, no schedule changes can be made without a dean's approval and late fees may apply.\n\n"
            "Log into the student portal to make any changes: portal.university.edu\n\n"
            "Registrar's Office\nUniversity Academic Affairs"
        ),
        days_ago=1,
    )

    insert_email(
        gmail,
        from_addr="Prof. Sarah Lin <s.lin@math.university.edu>",
        subject="MATH 220 — Wednesday office hours CANCELLED",
        body=(
            "Hi all,\n\n"
            "I need to cancel my office hours this Wednesday (4/22). "
            "I will hold extra office hours on Monday 2–4pm instead.\n\n"
            "Apologies for the short notice.\n\n"
            "— Prof. Lin"
        ),
        days_ago=0.5,
    )

    insert_email(
        gmail,
        from_addr="Financial Aid Office <finaid@university.edu>",
        subject="Action Required: Scholarship Renewal Deadline — April 30",
        body=(
            "Dear Clark,\n\n"
            "Your merit scholarship renewal application is due April 30th. "
            "Please log into the Financial Aid portal and complete the renewal form. "
            "Failure to submit by the deadline may result in loss of funding for the Fall semester.\n\n"
            "If you have questions, visit our office in Admin Building Room 104.\n\n"
            "Financial Aid Office"
        ),
        days_ago=1.5,
    )

    insert_email(
        gmail,
        from_addr="CS Department <cs-dept@university.edu>",
        subject="Undergraduate Research Symposium — This Friday 2–5pm",
        body=(
            "Hi CS students,\n\n"
            "The annual Undergraduate Research Symposium is happening this Friday, April 24th from 2–5pm "
            "in the Atrium of the Gates-Hillman Center.\n\n"
            "10+ student project demos, faculty judges, and prizes for top projects. "
            "Light refreshments provided. All are welcome!\n\n"
            "CS Department"
        ),
        days_ago=2,
    )

    insert_email(
        gmail,
        from_addr="Prof. Daniel Hartman <d.hartman@cs.university.edu>",
        subject="CS 301 — Midterm 2 location change",
        body=(
            "Hi class,\n\n"
            "Please note that Midterm 2 (April 28th, 7–9pm) has been moved from Doherty Hall A302 "
            "to Baker Hall A51 due to a room scheduling conflict.\n\n"
            "Everything else remains the same. Cheat sheet policy: one double-sided 8.5x11 page, handwritten only.\n\n"
            "— Prof. Hartman"
        ),
        days_ago=0.8,
    )


def seed_calendar(cal):
    print("\nCreating calendar events...")

    # Use today as the anchor — compute the Monday of the current week
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    # Find this Monday
    monday = today - timedelta(days=today.weekday())

    # Helper: nth weekday from this monday (0=Mon, 1=Tue, ... 6=Sun)
    def day(offset: int) -> datetime:
        return monday + timedelta(days=offset)

    # ── This week ──────────────────────────────────────────────────────────

    # Monday
    create_event(cal, "MATH 220 — Lecture", _dt(day(0), 10), _dt(day(0), 11),
                 location="Wean Hall 7500")
    create_event(cal, "Office Hours — Prof. Lin (EXTRA)", _dt(day(0), 14), _dt(day(0), 16),
                 location="Gates 210", description="Extra office hours — Wednesday OH cancelled")

    # Tuesday
    create_event(cal, "CS 301 — Lecture", _dt(day(1), 14), _dt(day(1), 15, 30),
                 location="Doherty Hall A302")
    create_event(cal, "CS 301 — Section", _dt(day(1), 13), _dt(day(1), 14),
                 location="Gates 4307", description="Weekly recitation")
    create_event(cal, "Robotics Club Meeting", _dt(day(1), 18), _dt(day(1), 19, 30),
                 location="Newell-Simon Hall 1507")

    # Wednesday
    create_event(cal, "MATH 220 — Lecture", _dt(day(2), 10), _dt(day(2), 11),
                 location="Wean Hall 7500")
    create_event(cal, "Study Group — CS 301 Pset 4", _dt(day(2), 19), _dt(day(2), 21),
                 location="Hunt Library 4th Floor")

    # Thursday
    create_event(cal, "CS 301 — Lecture", _dt(day(3), 14), _dt(day(3), 15, 30),
                 location="Doherty Hall A302")
    create_event(cal, "Office Hours — Prof. Hartman", _dt(day(3), 15, 30), _dt(day(3), 17),
                 location="Gates 210")

    # Friday
    create_event(cal, "MATH 220 — Lecture", _dt(day(4), 10), _dt(day(4), 11),
                 location="Wean Hall 7500")
    create_event(cal, "Undergraduate Research Symposium", _dt(day(4), 14), _dt(day(4), 17),
                 location="Gates-Hillman Center Atrium",
                 description="Annual CS undergrad research showcase — demos + prizes")

    # ── Next week ──────────────────────────────────────────────────────────

    # Next Monday
    create_event(cal, "MATH 220 — Lecture", _dt(day(7), 10), _dt(day(7), 11),
                 location="Wean Hall 7500")
    create_event(cal, "HIST 315 — Response Paper Due", _dt(day(7), 23, 59), _dt(day(8), 0, 29),
                 description="1500-word response paper on Ch. 7–9. Submit on Canvas.")

    # Next Tuesday
    create_event(cal, "CS 301 — Lecture", _dt(day(8), 14), _dt(day(8), 15, 30),
                 location="Doherty Hall A302")
    create_event(cal, "CS 301 — Section", _dt(day(8), 13), _dt(day(8), 14),
                 location="Gates 4307")
    create_event(cal, "Robotics Club Meeting", _dt(day(8), 18), _dt(day(8), 19, 30),
                 location="Newell-Simon Hall 1507")

    # Next Wednesday
    create_event(cal, "MATH 220 — Lecture", _dt(day(9), 10), _dt(day(9), 11),
                 location="Wean Hall 7500")
    create_event(cal, "BIO 150 — Lab Report Due", _dt(day(9), 23, 59), _dt(day(10), 0, 29),
                 description="Cell membrane permeability experiment writeup. Submit on Canvas.")

    # Next Thursday
    create_event(cal, "CS 301 — Lecture", _dt(day(10), 14), _dt(day(10), 15, 30),
                 location="Doherty Hall A302")
    create_event(cal, "MATH 260 — Checkpoint Quiz", _dt(day(10), 11), _dt(day(10), 12),
                 location="Porter Hall 100", description="Covers integration by parts + series")

    # Next Friday (Scholarship deadline)
    create_event(cal, "Scholarship Renewal Deadline", _dt(day(11), 17), _dt(day(11), 17, 30),
                 description="Financial Aid portal — merit scholarship renewal form due 5pm")

    # Two weeks out — CS Midterm 2
    create_event(cal, "CS 301 — Midterm 2", _dt(day(14) + timedelta(days=1), 19), _dt(day(14) + timedelta(days=1), 21),
                 location="Baker Hall A51",
                 description="Covers lectures 10–18. One double-sided cheat sheet allowed (handwritten).")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("Authenticating with Google...")
    creds = get_credentials()
    gmail = build("gmail", "v1", credentials=creds)
    cal = build("calendar", "v3", credentials=creds)

    seed_emails(gmail)
    seed_calendar(cal)

    print("\nDone! Check clarkkenthp2026@gmail.com and Google Calendar.")
