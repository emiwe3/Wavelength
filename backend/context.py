"""
context.py — builds a single structured text blob describing the student's
full academic situation. Injected into Claude's system prompt on every message.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List

import db
import calendar_sync
import gmail as gmail_mod
import canvas as canvas_mod
import slack_sync


def get_student_context(user: Dict[str, Any]) -> str:
    """
    Fetch live data from all connected sources and return a plain-text
    context block ready to be inserted into Claude's system prompt.
    """
    sections: List[str] = []
    now = datetime.now(timezone.utc)
    sections.append(f"Current date/time: {now.strftime('%A, %B %d, %Y at %I:%M %p UTC')}")

    # ── Google Calendar ────────────────────────────────────────────────────
    if user.get("ical_url"):
        try:
            events = calendar_sync.fetch_events(user["ical_url"], days_ahead=21)
            sections.append(_format_events(events))
        except Exception as exc:
            sections.append(f"[Calendar sync failed: {exc}]")
    else:
        sections.append("[No calendar connected]")

    # ── Canvas ────────────────────────────────────────────────────────────
    if user.get("canvas_token") and user.get("canvas_domain"):
        try:
            assignments = canvas_mod.get_upcoming_assignments(
                user["canvas_token"], user["canvas_domain"], days_ahead=21
            )
            sections.append(_format_assignments(assignments))
        except Exception as exc:
            sections.append(f"[Canvas sync failed: {exc}]")
    else:
        sections.append("[No Canvas connected]")

    # ── Gmail ──────────────────────────────────────────────────────────────
    if user.get("gmail_credentials"):
        try:
            emails, updated_creds = gmail_mod.get_academic_emails(
                user["gmail_credentials"], hours=48
            )
            sections.append(_format_emails(emails))
            # Persist refreshed token back to DB if it changed
            try:
                if updated_creds.get("token") != user["gmail_credentials"].get("token"):
                    db.upsert_user(user["phone"], gmail_credentials=updated_creds)
            except Exception:
                pass  # DB not critical — emails already appended
        except Exception as exc:
            sections.append(f"[Gmail sync failed: {exc}]")
    else:
        sections.append("[No Gmail connected]")

    # ── Slack ──────────────────────────────────────────────────────────────
    if user.get("slack_token") and user.get("slack_channel"):
        try:
            messages = slack_sync.get_announcements(
                user["slack_token"], user["slack_channel"]
            )
            sections.append(_format_slack(messages))
        except Exception as exc:
            sections.append(f"[Slack sync failed: {exc}]")
    else:
        sections.append("[No Slack connected]")

    return "\n\n".join(sections)


# ---------------------------------------------------------------------------
# Formatters
# ---------------------------------------------------------------------------

def _format_events(events: List[Dict[str, Any]]) -> str:
    if not events:
        return "UPCOMING CALENDAR EVENTS:\nNone in the next 3 weeks."

    lines = ["UPCOMING CALENDAR EVENTS:"]
    for e in events:
        start = _fmt_dt(e["start"])
        end = f" to {_fmt_dt(e['end'])}" if e.get("end") else ""
        loc = f", {e['location']}" if e.get("location") else ""
        lines.append(f"- {e['title']}: {start}{end}{loc}")
    return "\n".join(lines)


def _format_assignments(assignments: List[Dict[str, Any]]) -> str:
    if not assignments:
        return "CANVAS ASSIGNMENTS:\nNone due in the next 3 weeks."

    lines = ["CANVAS ASSIGNMENTS:"]
    for a in assignments:
        due = _fmt_dt(a["due_at"])
        status = "submitted" if a["submitted"] else "not submitted"
        pts = f" ({int(a['points'])} pts)" if a.get("points") else ""
        lines.append(f"- {a['course']}: {a['name']} — due {due}{pts} [{status}]")
    return "\n".join(lines)


def _format_emails(emails: List[Dict[str, Any]]) -> str:
    if not emails:
        return "RECENT ACADEMIC EMAILS (last 48h):\nNone."

    lines = ["RECENT ACADEMIC EMAILS (last 48h):"]
    for em in emails:
        lines.append(
            f"- From: {em['from']}\n"
            f"  Subject: {em['subject']}\n"
            f"  Preview: {em['preview']}"
        )
    return "\n".join(lines)


def _format_slack(messages: List[Dict[str, Any]]) -> str:
    if not messages:
        return "CAMPUS & CLUB ANNOUNCEMENTS (Slack):\nNone recently."

    lines = ["CAMPUS & CLUB ANNOUNCEMENTS (Slack):"]
    for m in messages:
        channel = f"[#{m['channel']}] " if m.get("channel") else ""
        lines.append(f"- {channel}{m['text']}")
    return "\n".join(lines)


def _fmt_dt(iso: str) -> str:
    try:
        dt = datetime.fromisoformat(iso)
        return dt.strftime("%a %b %d at %I:%M %p")
    except Exception:
        return iso
