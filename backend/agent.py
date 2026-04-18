import os
import threading
from collections import defaultdict
from typing import Any, Dict, List

import anthropic

import context as ctx_mod
import calendar_write
import db as db_mod

client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

MODEL = "claude-sonnet-4-6"
MAX_HISTORY = 20

SYSTEM_STATIC = """\
You are PulsePoint, an AI assistant that lives in iMessage and knows everything \
about this student's academic and campus life. You have visibility into their \
calendar events, assignments, emails, and Slack announcements — which include \
club meetings, campus events, social gatherings, and any other activity posted \
in their university or club Slack channels. Surface ALL of it, not just deadlines.

You can also add events to the student's Google Calendar using the create_calendar_event tool. \
Use it whenever the student asks you to add, schedule, or remember something on their calendar. \
Resolve relative dates like "tomorrow" or "next Friday" using the current date in the student context below. \
Before calling the tool, you must have a specific date AND time from the student — do not guess or assume. \
If either is missing, ask the student for the missing detail before creating the event.

Tone: warm, direct, like a smart friend who actually knows their schedule. \
No fluff, no filler. Be concise. Plain text only — no markdown, no bullet symbols, \
no asterisks. Use line breaks to separate thoughts.\
"""

TOOLS = [
    {
        "name": "create_calendar_event",
        "description": (
            "Add an event to the student's Google Calendar. "
            "Use this when the student asks to add, schedule, or remember something on their calendar. "
            "Resolve relative dates using the current date from the student context."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": "Event title or name",
                },
                "date": {
                    "type": "string",
                    "description": "Date in YYYY-MM-DD format",
                },
                "start_time": {
                    "type": "string",
                    "description": "Start time in HH:MM 24-hour format",
                },
                "end_time": {
                    "type": "string",
                    "description": "End time in HH:MM 24-hour format. Omit to default to 1 hour after start.",
                },
                "description": {
                    "type": "string",
                    "description": "Optional notes or details for the event",
                },
                "override": {
                    "type": "boolean",
                    "description": "Set to true to create the event even if there are scheduling conflicts. Only set after the student has confirmed they want to proceed despite the conflict.",
                },
            },
            "required": ["title", "date", "start_time"],
        },
    }
]

_history: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
CONTEXT_TTL = 900


def _refresh_context(user: Dict[str, Any]) -> None:
    try:
        ctx = ctx_mod.get_student_context(user)
        db_mod.set_cached_context(user["phone"], ctx)
    except Exception:
        pass


def _get_context(user: Dict[str, Any]) -> str:
    phone = user["phone"]
    cached = db_mod.get_cached_context(phone, ttl=CONTEXT_TTL)
    if cached:
        threading.Thread(target=_refresh_context, args=(user,), daemon=True).start()
        return cached
    try:
        ctx = ctx_mod.get_student_context(user)
        db_mod.set_cached_context(phone, ctx)
        return ctx
    except Exception as exc:
        return f"[Could not load student context: {exc}]"


def _build_system(student_context: str) -> list:
    return [
        {"type": "text", "text": SYSTEM_STATIC, "cache_control": {"type": "ephemeral"}},
        {"type": "text", "text": f"Student context (live data):\n{student_context}"},
    ]


def reply(user: Dict[str, Any], message: str) -> str:
    phone = user["phone"]
    student_context = _get_context(user)
    system = _build_system(student_context)

    _history[phone].append({"role": "user", "content": message})
    history = _history[phone][-MAX_HISTORY:]

    response = client.messages.create(
        model=MODEL,
        max_tokens=512,
        system=system,
        messages=history,
        tools=TOOLS,
    )

    if response.stop_reason == "tool_use":
        tool_block = next(b for b in response.content if b.type == "tool_use")
        tool_result = _run_tool(user, tool_block.name, tool_block.input)

        followup = client.messages.create(
            model=MODEL,
            max_tokens=512,
            system=system,
            messages=history + [
                {"role": "assistant", "content": response.content},
                {"role": "user", "content": [
                    {"type": "tool_result", "tool_use_id": tool_block.id, "content": tool_result}
                ]},
            ],
            tools=TOOLS,
        )
        reply_text = followup.content[0].text.strip()
    else:
        reply_text = response.content[0].text.strip()

    _history[phone].append({"role": "assistant", "content": reply_text})
    return reply_text


def _run_tool(user: Dict[str, Any], name: str, inputs: Dict[str, Any]) -> str:
    if name == "create_calendar_event":
        creds = user.get("gmail_credentials")
        if not creds:
            return "Error: no Google credentials found. The student needs to reconnect Google."

        if not inputs.get("override", False):
            conflicts = _check_conflicts(
                user, inputs["date"], inputs["start_time"], inputs.get("end_time")
            )
            if conflicts:
                return (
                    f"CONFLICT: The student already has the following event(s) at that time: {conflicts}. "
                    "Ask the student if they want to add it anyway. If they say yes, call this tool again with override=true."
                )

        try:
            event = calendar_write.create_event(
                credentials_dict=creds,
                title=inputs["title"],
                date=inputs["date"],
                start_time=inputs["start_time"],
                end_time=inputs.get("end_time"),
                description=inputs.get("description", ""),
            )
            return f"Event created: {event['title']} — {event['start']} to {event['end']}"
        except Exception as exc:
            return f"Error creating event: {exc}"
    return f"Unknown tool: {name}"


def _check_conflicts(user: Dict[str, Any], date: str, start_time: str, end_time: str = None) -> str:
    from datetime import datetime, timedelta, timezone
    import calendar_sync

    if not user.get("ical_url"):
        return ""

    try:
        new_start = datetime.fromisoformat(f"{date}T{start_time}:00").replace(tzinfo=timezone.utc)
        new_end = (
            datetime.fromisoformat(f"{date}T{end_time}:00").replace(tzinfo=timezone.utc)
            if end_time
            else new_start + timedelta(hours=1)
        )

        events = calendar_sync.fetch_events(user["ical_url"], days_ahead=30)
        conflicts = []
        for e in events:
            e_start = datetime.fromisoformat(e["start"])
            e_end = datetime.fromisoformat(e["end"]) if e.get("end") else e_start + timedelta(hours=1)
            if e_start.tzinfo is None:
                e_start = e_start.replace(tzinfo=timezone.utc)
            if e_end.tzinfo is None:
                e_end = e_end.replace(tzinfo=timezone.utc)
            if e_start < new_end and e_end > new_start:
                conflicts.append(e["title"])

        return ", ".join(conflicts) if conflicts else ""
    except Exception:
        return ""


def clear_history(phone: str) -> None:
    _history.pop(phone, None)
