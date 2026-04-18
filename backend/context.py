from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Any, Dict, List

import db
import calendar_sync
import gmail as gmail_mod
import canvas as canvas_mod
import slack_sync


def get_student_context(user: Dict[str, Any]) -> str:
    sections: List[str] = []
    now = datetime.now(timezone.utc)
    sections.append(f"Current date/time: {now.strftime('%A, %B %d, %Y at %I:%M %p UTC')}")

    results = _fetch_all(user)

    sections.append(results.get("calendar", "[No calendar connected]"))
    sections.append(results.get("canvas_assignments", "[No Canvas connected]"))
    if "canvas_announcements" in results:
        sections.append(results["canvas_announcements"])
    sections.append(results.get("gmail", "[No Gmail connected]"))
    sections.append(results.get("slack", "[No Slack connected]"))

    return "\n\n".join(sections)


def _fetch_all(user: Dict[str, Any]) -> Dict[str, str]:
    tasks = {}

    if user.get("ical_url"):
        tasks["calendar"] = lambda: _fetch_calendar(user)
    if user.get("canvas_token") and user.get("canvas_domain"):
        tasks["canvas_assignments"] = lambda: _fetch_canvas_assignments(user)
        tasks["canvas_announcements"] = lambda: _fetch_canvas_announcements(user)
    if user.get("gmail_credentials"):
        tasks["gmail"] = lambda: _fetch_gmail(user)
    if user.get("slack_token"):
        tasks["slack"] = lambda: _fetch_slack(user)

    results = {}
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = {executor.submit(fn): key for key, fn in tasks.items()}
        for future in as_completed(futures):
            key = futures[future]
            try:
                results[key] = future.result()
            except Exception as exc:
                results[key] = f"[{key} failed: {exc}]"

    return results


def _fetch_calendar(user: Dict[str, Any]) -> str:
    events = calendar_sync.fetch_events(user["ical_url"], days_ahead=21)
    return _format_events(events)


def _fetch_canvas_assignments(user: Dict[str, Any]) -> str:
    assignments = canvas_mod.get_upcoming_assignments(
        user["canvas_token"], user["canvas_domain"], days_ahead=21
    )
    return _format_assignments(assignments)


def _fetch_canvas_announcements(user: Dict[str, Any]) -> str:
    announcements = canvas_mod.get_announcements(
        user["canvas_token"], user["canvas_domain"]
    )
    return _format_announcements(announcements)


def _fetch_gmail(user: Dict[str, Any]) -> str:
    emails, updated_creds = gmail_mod.get_academic_emails(user["gmail_credentials"], hours=48)
    try:
        if updated_creds.get("token") != user["gmail_credentials"].get("token"):
            db.upsert_user(user["phone"], gmail_credentials=updated_creds)
    except Exception:
        pass
    return _format_emails(emails)


def _fetch_slack(user: Dict[str, Any]) -> str:
    token = user.get("slack_token")
    messages = slack_sync.get_announcements(token)
    return _format_slack(messages)


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


def _format_announcements(announcements: List[Dict[str, Any]]) -> str:
    if not announcements:
        return "CANVAS ANNOUNCEMENTS:\nNone recently."
    lines = ["CANVAS ANNOUNCEMENTS:"]
    for a in announcements:
        date = a.get("posted_at", "")[:10]
        author = f" ({a['author']})" if a.get("author") else ""
        lines.append(f"- [{a['course']}]{author} \"{a['title']}\" on {date}: {a['message']}")
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
