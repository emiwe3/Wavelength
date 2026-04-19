"""
messenger.py — send iMessages via the Photon iMessage Kit.
Set PHOTON_URL in .env to point at the running Photon server.
"""

import os
import httpx

PHOTON_URL = os.getenv("PHOTON_URL", "http://localhost:3000")


def send_message(phone: str, text: str) -> None:
    """POST a message to Photon which sends it via iMessage."""
    with httpx.Client(timeout=10) as client:
        client.post(f"{PHOTON_URL}/send", json={"phone": phone, "text": text})
