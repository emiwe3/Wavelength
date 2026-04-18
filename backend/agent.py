"""
agent.py — Claude-powered conversational agent.
Maintains per-user conversation history and injects live student context
into the system prompt on every message.
"""

import os
from collections import defaultdict
from typing import Any, Dict, List

import anthropic

import context as ctx_mod

client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

MODEL = "claude-sonnet-4-6"
MAX_HISTORY = 20  # messages kept per user (alternating user/assistant)

SYSTEM_PROMPT_TEMPLATE = """\
You are PulsePoint, an AI academic assistant that lives in iMessage. \
You have full visibility into this student's academic life — their calendar events, \
assignments, and emails — and your job is to help them stay on top of things.

Tone: warm, direct, like a smart friend who actually knows their schedule. \
No fluff, no filler. Be concise. Plain text only — no markdown, no bullet symbols, \
no asterisks. Use line breaks to separate thoughts.

Student context (live data):
{context}
"""

# In-memory conversation history keyed by phone number.
_history: Dict[str, List[Dict[str, str]]] = defaultdict(list)


def reply(user: Dict[str, Any], message: str) -> str:
    """
    Generate a reply for the given user and message.
    Updates conversation history in place.
    """
    phone = user["phone"]

    try:
        student_context = ctx_mod.get_student_context(user)
    except Exception as exc:
        student_context = f"[Could not load student context: {exc}]"

    system_prompt = SYSTEM_PROMPT_TEMPLATE.format(context=student_context)

    _history[phone].append({"role": "user", "content": message})

    history = _history[phone][-MAX_HISTORY:]

    response = client.messages.create(
        model=MODEL,
        max_tokens=1024,
        system=system_prompt,
        messages=history,
    )

    reply_text = response.content[0].text.strip()

    _history[phone].append({"role": "assistant", "content": reply_text})

    return reply_text


def clear_history(phone: str) -> None:
    """Reset conversation history for a user (e.g. after onboarding)."""
    _history.pop(phone, None)
