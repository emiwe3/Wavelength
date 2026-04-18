"""
bot.py — PulsePoint iMessage bot.
Listens for incoming iMessages, replies via Claude, and mirrors to Slack.
"""

import os
import sys
import time
import threading
from dotenv import load_dotenv

load_dotenv()

import db
import agent
import imessage
import slack_sync
from slack_sdk import WebClient as SlackClient

SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN")
SLACK_CHANNEL_ID = os.getenv("SLACK_CHANNEL_ID")

_slack = SlackClient(token=SLACK_BOT_TOKEN) if SLACK_BOT_TOKEN else None


def _post_slack(text: str) -> None:
    if _slack and SLACK_CHANNEL_ID:
        try:
            _slack.chat_postMessage(channel=SLACK_CHANNEL_ID, text=text)
        except Exception:
            pass


def _post_deadline_digest() -> None:
    """Post upcoming Canvas deadlines to Slack for all users."""
    from db import _connect
    with _connect() as conn:
        rows = conn.execute("SELECT * FROM users").fetchall()

    import canvas as canvas_mod
    import context as ctx_mod

    for row in rows:
        user = dict(row)
        if not user.get("canvas_token"):
            continue
        try:
            import json
            if user.get("gmail_credentials") and isinstance(user["gmail_credentials"], str):
                user["gmail_credentials"] = json.loads(user["gmail_credentials"])
            assignments = canvas_mod.get_upcoming_assignments(
                user["canvas_token"], user["canvas_domain"]
            )
            if not assignments:
                continue
            lines = [f"📚 Deadline digest for {user['phone']}:"]
            for a in assignments[:5]:
                lines.append(f"  • {a['course']}: {a['name']} — due {a['due_at'][:10]}")
            _post_slack("\n".join(lines))
        except Exception as exc:
            print(f"Digest error for {user.get('phone')}: {exc}")


def _hourly_sync() -> None:
    while True:
        time.sleep(3600)
        print("🔄 Hourly Canvas sync...")
        try:
            _post_deadline_digest()
        except Exception as exc:
            print(f"Hourly sync error: {exc}")


def on_message(chat_guid: str, text: str, sender: str) -> None:
    print(f"📩 Received: \"{text}\" from {chat_guid}")

    # Look up user by phone number (strip "any;-;" prefix)
    phone = sender if not sender.startswith("any") else chat_guid.split(";")[-1]
    user = db.get_user(phone)
    if not user:
        db.upsert_user(phone)
        user = db.get_user(phone)

    try:
        reply = agent.reply(user, text)
    except Exception as exc:
        reply = f"Sorry, something went wrong: {exc}"

    imessage.send(chat_guid, reply)
    print(f"📤 Replied: \"{reply}\"")

    _post_slack(f"💬 *iMessage from {chat_guid}*\n> {text}\n\n🤖 *PulsePoint:* {reply}")


def main() -> None:
    print("🤖 PulsePoint is starting...")

    # Post initial deadline digest
    try:
        _post_deadline_digest()
    except Exception as exc:
        print(f"Initial digest error: {exc}")

    # Start hourly sync in background
    threading.Thread(target=_hourly_sync, daemon=True).start()

    # Start iMessage listener (blocking)
    print("👂 Listening for iMessages...")
    imessage.listen_sync(on_message)


if __name__ == "__main__":
    main()
