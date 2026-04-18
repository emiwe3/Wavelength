"""
imessage.py — send and receive iMessages via the Photon AI server (gRPC).
Matches the credentials in client.ts: address + token.
Falls back to AppleScript for sending if the server is unavailable.
"""

import json
import os
import subprocess
import threading
from typing import Callable, Optional

import httpx
import websockets
import asyncio

SERVER_ADDRESS = os.getenv("IMESSAGE_SERVER_ADDRESS", "558aa7e3-ba58-4042-b8ea-1e5775c0eaad")
SERVER_TOKEN = os.getenv("IMESSAGE_SERVER_TOKEN", "FjAevbIPQjljgJIzAn0SGrfwgnU3jSw-e2kIHFbHZf4")
SERVER_URL = os.getenv("IMESSAGE_SERVER_URL", "http://localhost:1234")
WS_URL = os.getenv("IMESSAGE_WS_URL", "ws://localhost:1234")


def send(chat_guid: str, text: str) -> None:
    """Send an iMessage. Tries the Photon server first, falls back to AppleScript."""
    try:
        _send_via_server(chat_guid, text)
    except Exception:
        _send_via_applescript(chat_guid, text)


def _send_via_server(chat_guid: str, text: str) -> None:
    with httpx.Client(timeout=10) as client:
        resp = client.post(
            f"{SERVER_URL}/api/v1/message/text",
            headers={"Authorization": f"Bearer {SERVER_TOKEN}"},
            json={"chatGuid": chat_guid, "message": text},
        )
        resp.raise_for_status()


def _send_via_applescript(address: str, text: str) -> None:
    # Strip "any;-;" prefix if present to get raw phone/email
    if ";" in address:
        address = address.split(";")[-1]
    escaped = text.replace("\\", "\\\\").replace('"', '\\"')
    script = (
        f'tell application "Messages" to send "{escaped}" '
        f'to buddy "{address}" of service "iMessage"'
    )
    subprocess.run(["osascript", "-e", script], check=True)


async def listen(on_message: Callable[[str, str, str], None]) -> None:
    """
    Connect to the Photon server WebSocket and call on_message(chat_guid, text, sender)
    for every inbound message.
    """
    ws_uri = f"{WS_URL}/ws?token={SERVER_TOKEN}"
    async with websockets.connect(ws_uri) as ws:
        async for raw in ws:
            try:
                event = json.loads(raw)
                if event.get("type") != "message.received":
                    continue
                msg = event.get("message", {})
                text = msg.get("text", "").strip()
                if not text or msg.get("isFromMe"):
                    continue
                chat_guid = event.get("chatGuid", "")
                sender = msg.get("handle", {}).get("address", "unknown")
                on_message(chat_guid, text, sender)
            except Exception:
                continue


def listen_sync(on_message: Callable[[str, str, str], None]) -> None:
    """Blocking wrapper around listen() for use in a plain thread."""
    asyncio.run(listen(on_message))
