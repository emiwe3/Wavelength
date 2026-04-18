"""
test_all.py — test all data channels: Canvas, Slack, Gmail, Google Calendar, and AI.
Run from the backend/ directory: python test_all.py
"""

import os
import sys
from dotenv import load_dotenv

load_dotenv()

CANVAS_TOKEN = os.getenv("CANVAS_API_TOKEN") or os.getenv("CANVAS_CLIENT_ID") or None
CANVAS_DOMAIN = os.getenv("CANVAS_BASE_URL", "").replace("https://", "").rstrip("/") or os.getenv("CANVAS_DOMAIN") or None
SLACK_TOKEN = os.getenv("SLACK_BOT_TOKEN")
ICAL_URL = os.getenv("GOOGLE_ICAL_URL")
ANTHROPIC_KEY = os.getenv("ANTHROPIC_API_KEY")


def section(title: str) -> None:
    print(f"\n{'='*50}")
    print(f"  {title}")
    print('='*50)


# ── Canvas ────────────────────────────────────────────────────────────────────
section("📚 CANVAS")
if CANVAS_TOKEN and CANVAS_DOMAIN:
    try:
        import canvas as canvas_mod
        assignments = canvas_mod.get_upcoming_assignments(CANVAS_TOKEN, CANVAS_DOMAIN)
        announcements = canvas_mod.get_announcements(CANVAS_TOKEN, CANVAS_DOMAIN)
        print(f"✅ Connected — {len(assignments)} upcoming assignments, {len(announcements)} announcements")
        for a in assignments[:3]:
            print(f"  • {a['course']}: {a['name']} — due {a['due_at'][:10]}")
        for ann in announcements[:2]:
            print(f"  📢 [{ann['course']}] {ann['title']}")
    except Exception as exc:
        print(f"❌ Canvas error: {exc}")
else:
    print("⚠️  No Canvas token/domain in .env (CANVAS_API_TOKEN + CANVAS_BASE_URL)")


# ── Slack ─────────────────────────────────────────────────────────────────────
section("💬 SLACK")
if SLACK_TOKEN:
    try:
        import slack_sync
        messages = slack_sync.get_announcements(SLACK_TOKEN)
        channels = list({m["channel"] for m in messages})
        print(f"✅ Connected — {len(messages)} messages across {len(channels)} channels")
        for m in messages[:4]:
            preview = m["text"][:80].replace("\n", " ")
            print(f"  #{m['channel']}: {preview}")
    except Exception as exc:
        print(f"❌ Slack error: {exc}")
else:
    print("⚠️  No SLACK_BOT_TOKEN in .env")


# ── Google Calendar ───────────────────────────────────────────────────────────
section("📅 GOOGLE CALENDAR")
if ICAL_URL:
    try:
        import calendar_sync
        events = calendar_sync.fetch_events(ICAL_URL, days_ahead=21)
        print(f"✅ Connected — {len(events)} upcoming events")
        for e in events[:3]:
            print(f"  • {e['title']} — {e['start'][:16]}")
    except Exception as exc:
        print(f"❌ Calendar error: {exc}")
else:
    print("⚠️  No GOOGLE_ICAL_URL in .env")


# ── Gmail ─────────────────────────────────────────────────────────────────────
section("📧 GMAIL")
import sqlite3, json
from pathlib import Path
db_path = Path(__file__).parent / "users.db"
gmail_creds = None
try:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT gmail_credentials FROM users WHERE gmail_credentials IS NOT NULL LIMIT 1").fetchone()
    conn.close()
    if row:
        gmail_creds = json.loads(row["gmail_credentials"])
except Exception:
    pass

if gmail_creds:
    try:
        import gmail as gmail_mod
        emails, _ = gmail_mod.get_academic_emails(gmail_creds, hours=48)
        print(f"✅ Connected — {len(emails)} academic emails in last 48h")
        for em in emails[:3]:
            print(f"  • From: {em['from'][:50]}")
            print(f"    Subject: {em['subject']}")
    except Exception as exc:
        print(f"❌ Gmail error: {exc}")
else:
    print("⚠️  No Gmail credentials in DB — complete OAuth flow via http://localhost:8000/auth/google/start")


# ── AI (full context) ─────────────────────────────────────────────────────────
section("🤖 AI (FULL CONTEXT)")
if ANTHROPIC_KEY:
    try:
        import db as db_mod
        import agent as agent_mod

        # Use first user in DB, or a dummy
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM users WHERE phone = '+19165448193'").fetchone() or \
              conn.execute("SELECT * FROM users LIMIT 1").fetchone()
        conn.close()

        if row:
            user = dict(row)
            if user.get("gmail_credentials") and isinstance(user["gmail_credentials"], str):
                user["gmail_credentials"] = json.loads(user["gmail_credentials"])
        else:
            user = {"phone": "test"}

        # Fill in any missing credentials from .env for testing
        user.setdefault("canvas_token", CANVAS_TOKEN)
        user.setdefault("canvas_domain", CANVAS_DOMAIN)
        user.setdefault("ical_url", ICAL_URL)
        user.setdefault("slack_token", SLACK_TOKEN)
        user.setdefault("slack_channel", os.getenv("SLACK_CHANNEL_ID"))
        if not user.get("gmail_credentials"):
            user["gmail_credentials"] = gmail_creds

        import context as ctx_mod
        ctx = ctx_mod.get_student_context(user)
        print("Context preview (first 300 chars):")
        print(ctx[:300])
        print("\n--- Asking: 'what's going on this week?' ---")
        reply = agent_mod.reply(user, "what's going on this week?")
        print(f"\nPulsePoint: {reply}")
    except Exception as exc:
        print(f"❌ AI error: {exc}")
else:
    print("⚠️  No ANTHROPIC_API_KEY in .env")

print("\n" + "="*50)
print("  Done.")
print("="*50 + "\n")
