"""
scheduler.py — proactive reminder engine.

Jobs:
  - Every 60 min : check all users for 24h and 72h deadline warnings
  - Daily 8am    : morning briefing
  - Sunday 8pm   : weekly digest
"""

from datetime import datetime, timedelta, timezone

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

import db
import agent
import messenger
import maps as maps_mod
import canvas as canvas_mod
import calendar_sync


# ---------------------------------------------------------------------------
# Deadline reminders (runs every hour)
# ---------------------------------------------------------------------------

def check_deadline_reminders():
    for user in db.get_all_users():
        try:
            _check_user(user)
        except Exception:
            continue


def _check_user(user: dict):
    now = datetime.now(timezone.utc)
    reminders_sent = user.get("reminders_sent") or {}
    changed = False

    deadlines = _collect_deadlines(user)

    for item_id, title, due_dt, location in deadlines:
        hours_left = (due_dt - now).total_seconds() / 3600

        for window, lower, label in [(1, 0, "1h"), (24, 1, "24h"), (72, 24, "72h")]:
            key = f"{item_id}_{label}"
            if lower < hours_left <= window and key not in reminders_sent:
                if label == "1h":
                    travel_info = ""
                    lat = user.get("current_lat")
                    lng = user.get("current_lng")
                    if lat and lng and location:
                        eta = maps_mod.get_leave_by(lat, lng, location, due_dt.isoformat())
                        if eta:
                            travel_info = (
                                f" It's at {location}. "
                                f"{eta['travel_time']} — leave by {eta['leave_by']}."
                            )
                    prompt = (
                        f"Send an urgent last-chance warning that '{title}' is due in "
                        f"under an hour (about {int(hours_left * 60)} minutes). Be direct and alarming — "
                        f"tell them to drop everything and go right now.{travel_info}"
                    )
                else:
                    prompt = (
                        f"Send a proactive {label} reminder that '{title}' is due in "
                        f"about {int(hours_left)} hours. Be warm and specific — mention "
                        f"what it is, when it's due, and one concrete next step."
                    )
                text = agent.proactive_message(user, prompt)
                messenger.send_message(user["phone"], text)
                reminders_sent[key] = now.isoformat()
                changed = True

    if changed:
        db.upsert_user(user["phone"], reminders_sent=reminders_sent)


def _collect_deadlines(user: dict):
    """Return list of (id, title, due_datetime) from all connected sources."""
    items = []

    # Canvas assignments
    if user.get("canvas_token") and user.get("canvas_domain"):
        try:
            assignments = canvas_mod.get_upcoming_assignments(
                user["canvas_token"], user["canvas_domain"], days_ahead=7
            )
            for a in assignments:
                if not a.get("submitted"):
                    due = datetime.fromisoformat(a["due_at"].replace("Z", "+00:00"))
                    item_id = f"canvas_{a['course']}_{a['name']}"
                    items.append((item_id, f"{a['course']}: {a['name']}", due, None))
        except Exception:
            pass

    # Calendar events (exams, quizzes, due dates)
    if user.get("ical_url"):
        try:
            events = calendar_sync.fetch_events(user["ical_url"], days_ahead=7)
            deadline_keywords = ["due", "exam", "quiz", "midterm", "final", "deadline", "test"]
            for e in events:
                title_lower = e["title"].lower()
                if any(kw in title_lower for kw in deadline_keywords):
                    due = datetime.fromisoformat(e["start"])
                    if due.tzinfo is None:
                        due = due.replace(tzinfo=timezone.utc)
                    item_id = f"cal_{e['title']}_{e['start'][:10]}"
                    items.append((item_id, e["title"], due, e.get("location")))
        except Exception:
            pass

    return items


# ---------------------------------------------------------------------------
# Morning briefing (8am daily)
# ---------------------------------------------------------------------------

def send_morning_briefings():
    for user in db.get_all_users():
        try:
            text = agent.proactive_message(
                user,
                "Send the student their morning briefing. Cover: what's due today, "
                "today's schedule, and the biggest thing coming up in the next 48 hours. "
                "Keep it short — 5 lines max.",
            )
            messenger.send_message(user["phone"], text)
        except Exception:
            continue


# ---------------------------------------------------------------------------
# Weekly digest (Sunday 8pm)
# ---------------------------------------------------------------------------

def send_weekly_digest():
    for user in db.get_all_users():
        try:
            text = agent.proactive_message(
                user,
                "Send the student their Sunday night weekly digest. Cover the full week ahead: "
                "all deadlines, exams, and key events. Flag the heaviest days and give one "
                "concrete recommendation for what to start tonight.",
            )
            messenger.send_message(user["phone"], text)
        except Exception:
            continue


# ---------------------------------------------------------------------------
# Scheduler setup
# ---------------------------------------------------------------------------

def start() -> BackgroundScheduler:
    scheduler = BackgroundScheduler(timezone="America/New_York")

    # Deadline checks — every 60 minutes
    scheduler.add_job(check_deadline_reminders, "interval", minutes=60, id="deadline_check")

    # Morning briefing — 8am every day
    scheduler.add_job(send_morning_briefings, CronTrigger(hour=8, minute=0), id="morning_briefing")

    # Weekly digest — Sunday 8pm
    scheduler.add_job(send_weekly_digest, CronTrigger(day_of_week="sun", hour=20, minute=0), id="weekly_digest")

    scheduler.start()
    return scheduler
