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

You can schedule future iMessages using the schedule_message tool — use this for reminders or \
timed messages the student wants sent later. You can also add events to the student's Google Calendar using the create_calendar_event tool. \
Use it whenever the student asks you to add, schedule, or remember something on their calendar, \
or when they send you an event flyer image — extract the event details from the image and offer to add it. \
Resolve relative dates like "tomorrow" or "next Friday" using the current date in the student context below. \
Before calling the tool, you must have a specific date AND time from the student — do not guess or assume. \
If either is missing, ask the student for the missing detail before creating the event.

Tone: warm, direct, like a smart friend who actually knows their schedule. \
No fluff, no filler. Be concise. Plain text only — no markdown, no bullet symbols, \
no asterisks. Use line breaks to separate thoughts.\
"""

TOOLS = [
    {
        "name": "schedule_message",
        "description": (
            "Schedule an iMessage to be sent at a future time. "
            "Use when the student asks to schedule a reminder or message to themselves or a contact. "
            "Resolve relative times like 'tomorrow at 9am' using the current date in the student context."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "recipient": {
                    "type": "string",
                    "description": "Phone number to send to (e.g. +16175551234), or 'self' to send to the student.",
                },
                "text": {
                    "type": "string",
                    "description": "The message text to send.",
                },
                "scheduled_for": {
                    "type": "string",
                    "description": "ISO 8601 datetime when to send, always including the EDT offset, e.g. 2026-04-19T09:00:00-04:00. Derive the send time from the current date/time in the student context.",
                },
            },
            "required": ["recipient", "text", "scheduled_for"],
        },
    },
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
CONTEXT_TTL = 120


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


def reply(user: Dict[str, Any], message: str, image_base64: str = None, image_media_type: str = None, audio_path: str = None) -> tuple:
    import audio as audio_mod

    phone = user["phone"]

    if audio_path:
        try:
            transcribed = audio_mod.transcribe(audio_path)
            message = transcribed
        except Exception as exc:
            message = message or "[Voice message — transcription failed]"

    student_context = _get_context(user)
    system = _build_system(student_context)

    if image_base64:
        caption = message or "I sent you an image. If it's an event flyer, extract the event details and offer to add it to my calendar."
        user_content = [
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": image_media_type or "image/jpeg",
                    "data": image_base64,
                },
            },
            {"type": "text", "text": caption},
        ]
        # Store image in history only for this turn; replace with text summary afterward
        _history[phone].append({"role": "user", "content": user_content})
        history = _history[phone][-MAX_HISTORY:]
        # Replace the image entry with a plain-text summary so future turns stay clean
        _history[phone][-1] = {"role": "user", "content": f"[Sent an image] {caption}"}
    else:
        _history[phone].append({"role": "user", "content": message})
        history = _history[phone][-MAX_HISTORY:]

    response = client.messages.create(
        model=MODEL,
        max_tokens=512,
        system=system,
        messages=history,
        tools=TOOLS,
    )

    actions = {}

    if response.stop_reason == "tool_use":
        tool_block = next(b for b in response.content if b.type == "tool_use")
        tool_result, tool_actions = _run_tool(user, tool_block.name, tool_block.input)
        actions.update(tool_actions)

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

    return reply_text, actions


def _run_tool(user: Dict[str, Any], name: str, inputs: Dict[str, Any]) -> tuple:
    if name == "schedule_message":
        recipient = inputs.get("recipient", "self")
        if recipient == "self":
            recipient = user.get("phone", "")
        text = inputs.get("text", "")
        scheduled_for = inputs.get("scheduled_for", "")
        action = {"recipient": recipient, "text": text, "scheduled_for": scheduled_for}
        return f"Message scheduled to {recipient} at {scheduled_for}: \"{text}\"", {"scheduled_message": action}

    if name == "create_calendar_event":
        creds = user.get("gmail_credentials")
        if not creds:
            return "Error: no Google credentials found. The student needs to reconnect Google.", {}

        if not inputs.get("override", False):
            conflicts = _check_conflicts(
                user, inputs["date"], inputs["start_time"], inputs.get("end_time")
            )
            if conflicts:
                return (
                    f"CONFLICT: The student already has the following event(s) at that time: {conflicts}. "
                    "Ask the student if they want to add it anyway. If they say yes, call this tool again with override=true.",
                    {},
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
            return f"Event created: {event['title']} — {event['start']} to {event['end']}", {}
        except Exception as exc:
            return f"Error creating event: {exc}", {}
    return f"Unknown tool: {name}", {}


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
