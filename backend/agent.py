import os
import threading
from collections import defaultdict
from typing import Any, Dict, List

import anthropic

import context as ctx_mod
import calendar_write
import maps as maps_mod
import db as db_mod

client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

MODEL = "claude-sonnet-4-6"
MAX_HISTORY = 10

SYSTEM_STATIC = """\
You are Wavelength, an AI assistant that lives in iMessage and knows everything \
about this student's academic and campus life. You have visibility into their \
calendar events, assignments, emails, and Slack announcements — which include \
club meetings, campus events, social gatherings, and any other activity posted \
in their university or club Slack channels. Surface ALL of it, not just deadlines.

You can schedule future iMessages using the schedule_message tool — use this for reminders or \
timed messages the student wants sent later. You can also add or delete events on the student's Google Calendar using the create_calendar_event and delete_calendar_event tools. \
Use create_calendar_event whenever the student asks to add, schedule, or remember something on their calendar. \
When the student sends any image, immediately call extract_events_from_image to extract and add all events — never ask the student to type the details manually. \
You can give directions using the get_directions tool. \
Resolve relative dates like "tomorrow" or "next Friday" using the current date in the student context below. \
Before calling the tool, you must have a specific date AND time from the student — do not guess or assume. \
If either is missing, ask the student for the missing detail before creating the event.

Plain text only — no markdown, no bullet symbols, no asterisks. Use line breaks to separate thoughts.

PERSONALITY: Adapt your tone based on the student's current mood or request. \
If they ask you to be kinder, more aggressive, more hype, more chill, more blunt, etc. — fully commit to it. \
When the student sets a vibe, use the set_personality tool to remember it, then immediately adopt that tone. \
Default tone: warm, direct, like a smart friend who actually knows their schedule.\
"""

PERSONALITIES = {
    "sad": "The student is feeling sad. Be extra warm, gentle, and emotionally supportive. Acknowledge their feelings before getting to business.",
    "unmotivated": "The student is feeling unmotivated. Be energetic, hype them up, use motivational language, push them to get things done. Be a drill sergeant if needed.",
    "stressed": "The student is stressed. Be calm, reassuring, and help them prioritize. Break things into small steps.",
    "happy": "The student is in a great mood. Match their energy — be upbeat and fun.",
    "focused": "The student wants to focus. Be super concise, no small talk, just the facts.",
    "chill": "Keep it super casual and low-key. Short responses, relaxed vibe.",
    "default": "Warm, direct, like a smart friend who actually knows their schedule.",
}

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
    },
    {
        "name": "set_personality",
        "description": "Save the student's requested personality/mood so it persists across messages. Call this whenever the student asks you to change your tone, vibe, or energy (e.g. 'be more kind', 'hype me up', 'be aggressive', 'be chill').",
        "input_schema": {
            "type": "object",
            "properties": {
                "mood": {
                    "type": "string",
                    "description": "A short label for the mood (e.g. 'sad', 'unmotivated', 'stressed', 'happy', 'focused', 'chill', or a custom description)",
                },
                "description": {
                    "type": "string",
                    "description": "A sentence describing how you should behave in this mode",
                },
            },
            "required": ["mood", "description"],
        },
    },
    {
        "name": "delete_calendar_event",
        "description": "Delete an event from the student's Google Calendar. First search for matching events, confirm with the student which one to delete, then delete it.",
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["search", "delete"],
                    "description": "Use 'search' first to find matching events, then 'delete' with the event_id to remove it.",
                },
                "query": {
                    "type": "string",
                    "description": "Search term to find the event (for action=search)",
                },
                "event_id": {
                    "type": "string",
                    "description": "The event ID to delete (for action=delete)",
                },
                "event_title": {
                    "type": "string",
                    "description": "Title of the event being deleted, for confirmation message",
                },
            },
            "required": ["action"],
        },
    },
    {
        "name": "extract_events_from_image",
        "description": (
            "Extract all events, deadlines, assignments, and meetings from the image the student just sent "
            "(a flyer, syllabus, screenshot, or document) and add them all to their Google Calendar at once. "
            "Call this automatically whenever the student sends an image that contains event or schedule information."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "get_directions",
        "description": "Generate a Google Maps directions link to a destination. Use whenever the student asks about directions, how to get somewhere, where a place is, or how long it takes to get there.",
        "input_schema": {
            "type": "object",
            "properties": {
                "destination": {
                    "type": "string",
                    "description": "The destination address or place name",
                },
                "origin": {
                    "type": "string",
                    "description": "Optional origin address. Leave blank to use the user's current location.",
                },
                "mode": {
                    "type": "string",
                    "enum": ["walking", "driving", "transit", "bicycling"],
                    "description": "Travel mode. Default: walking.",
                },
            },
            "required": ["destination"],
        },
    },
]

_history: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
CONTEXT_TTL = 600


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


def _build_system(student_context: str, user: Dict[str, Any] = None) -> list:
    personality = ""
    if user:
        mood = db_mod.get_preference(user["phone"], "personality_mood")
        desc = db_mod.get_preference(user["phone"], "personality_desc")
        if mood and desc:
            personality = f"\nCURRENT MOOD/VIBE: {mood.upper()} — {desc}"
        elif mood and mood in PERSONALITIES:
            personality = f"\nCURRENT MOOD/VIBE: {mood.upper()} — {PERSONALITIES[mood]}"
    return [
        {"type": "text", "text": SYSTEM_STATIC + personality, "cache_control": {"type": "ephemeral"}},
        {"type": "text", "text": f"Student context (live data):\n{student_context}", "cache_control": {"type": "ephemeral"}},
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
    system = _build_system(student_context, user)

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

    messages = list(history)
    reply_text = ""
    actions = {}

    for _ in range(3):  # max tool-call rounds
        response = client.messages.create(
            model=MODEL,
            max_tokens=512,
            system=system,
            messages=messages,
            tools=TOOLS,
        )

        if response.stop_reason != "tool_use":
            text_block = next((b for b in response.content if hasattr(b, "text")), None)
            reply_text = text_block.text.strip() if text_block else ""
            break

        # Run ALL tool_use blocks and collect results
        tool_results = []
        for block in response.content:
            if block.type != "tool_use":
                continue
            result, tool_actions = _run_tool(user, block.name, block.input,
                                             image_base64=image_base64,
                                             image_media_type=image_media_type)
            actions.update(tool_actions)
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": result,
            })

        messages = messages + [
            {"role": "assistant", "content": response.content},
            {"role": "user", "content": tool_results},
        ]

    _history[phone].append({"role": "assistant", "content": reply_text})

    return reply_text, actions


def _run_tool(user: Dict[str, Any], name: str, inputs: Dict[str, Any],
              image_base64: str = None, image_media_type: str = None) -> tuple:
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

    if name == "set_personality":
        mood = inputs.get("mood", "default")
        description = inputs.get("description", "")
        db_mod.set_preference(user["phone"], "personality_mood", mood)
        db_mod.set_preference(user["phone"], "personality_desc", description)
        return f"Personality set to '{mood}'. Adopt this tone immediately: {description}", {}

    if name == "delete_calendar_event":
        creds = user.get("gmail_credentials")
        if not creds:
            return "Error: no Google credentials found.", {}
        action = inputs.get("action")
        if action == "search":
            query = inputs.get("query", "")
            events = calendar_write.find_events(creds, query)
            if not events:
                return f"No upcoming events found matching '{query}'.", {}
            lines = [f"Found {len(events)} event(s):"]
            for e in events:
                lines.append(f"- \"{e['title']}\" on {e['start']} (id: {e['id']})")
            return "\n".join(lines), {}
        elif action == "delete":
            event_id = inputs.get("event_id", "")
            title = inputs.get("event_title", "the event")
            if not event_id:
                return "Error: event_id required to delete.", {}
            try:
                calendar_write.delete_event(creds, event_id)
                return f"Deleted \"{title}\" from your calendar.", {}
            except Exception as e:
                return f"Failed to delete event: {e}", {}
        return "Error: unknown action.", {}

    if name == "extract_events_from_image":
        if not image_base64:
            return "No image available to extract events from.", {}
        result = parse_image(user, image_base64, image_media_type or "image/jpeg")
        return result, {}

    if name == "get_directions":
        from urllib.parse import quote
        destination = inputs["destination"]
        origin = inputs.get("origin", "")
        mode_map = {"driving": "driving", "walking": "walking", "transit": "transit", "bicycling": "bicycling"}
        mode = mode_map.get(inputs.get("mode", "walking"), "walking")
        dest_enc = quote(destination)
        if origin:
            url = f"https://www.google.com/maps/dir/?api=1&origin={quote(origin)}&destination={dest_enc}&travelmode={mode}"
        else:
            url = f"https://www.google.com/maps/dir/?api=1&destination={dest_enc}&travelmode={mode}"
        return f"Google Maps link: {url}", {}

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


def proactive_message(user: Dict[str, Any], prompt: str) -> str:
    """Generate a proactive outbound message — no conversation history."""
    student_context = _get_context(user)
    response = client.messages.create(
        model=MODEL,
        max_tokens=512,
        system=_build_system(student_context),
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text.strip()


def clear_history(phone: str) -> None:
    _history.pop(phone, None)


def parse_image(user: Dict[str, Any], image_base64: str, media_type: str = "image/jpeg") -> str:
    """Extract events from a syllabus or flyer image and add them to Google Calendar."""
    import json

    extraction_response = client.messages.create(
        model=MODEL,
        max_tokens=2048,
        messages=[{
            "role": "user",
            "content": [
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": media_type,
                        "data": image_base64,
                    },
                },
                {
                    "type": "text",
                    "text": (
                        "Extract every event, deadline, assignment, exam, office hours, "
                        "and meeting from this image. Return ONLY a JSON array, no other text. "
                        "Each item: {\"title\": str, \"date\": \"YYYY-MM-DD\", "
                        "\"start_time\": \"HH:MM\", \"end_time\": \"HH:MM\" (optional), "
                        "\"description\": str (optional)}. "
                        f"Today is {__import__('datetime').date.today().isoformat()}. "
                        "Resolve relative dates. If no time is given for a deadline, use 23:59. "
                        "If no year is given, assume the current or next upcoming occurrence."
                    ),
                },
            ],
        }],
    )

    raw = extraction_response.content[0].text.strip()
    # Strip markdown code fences if present
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    raw = raw.strip()

    try:
        events = json.loads(raw)
    except json.JSONDecodeError:
        return "I couldn't parse the events from that image. Try a clearer photo."

    if not events:
        return "I didn't find any events or deadlines in that image."

    creds = user.get("gmail_credentials")
    added = []
    skipped = []

    for e in events:
        if not e.get("title") or not e.get("date") or not e.get("start_time"):
            skipped.append(e.get("title", "unnamed"))
            continue
        try:
            calendar_write.create_event(
                credentials_dict=creds,
                title=e["title"],
                date=e["date"],
                start_time=e["start_time"],
                end_time=e.get("end_time"),
                description=e.get("description", "Added by Wavelength"),
            )
            added.append(f"{e['title']} ({e['date']})")
        except Exception as exc:
            skipped.append(f"{e.get('title', 'unnamed')} ({exc})")

    lines = [f"Found {len(events)} item(s) in that image."]
    if added:
        lines.append(f"Added to your calendar:\n" + "\n".join(f"• {a}" for a in added))
    if skipped:
        lines.append(f"Skipped (missing info): {', '.join(skipped)}")
    return "\n\n".join(lines)
