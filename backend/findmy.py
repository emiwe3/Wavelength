"""
findmy.py — Poll Apple Find My Friends via pyicloud and update user locations.
Runs as a background thread. Matches friends by phone number to registered users.
"""

import os
import time
import threading
from typing import Optional

from pyicloud import PyiCloudService
from pyicloud.exceptions import PyiCloudFailedLoginException

import db

APPLE_ID = os.getenv("APPLE_ID", "").strip().strip('"')
APPLE_PASSWORD = os.getenv("APPLE_PASSWORD", "").strip().strip('"')
POLL_INTERVAL = 300  # 5 minutes

_api: Optional[PyiCloudService] = None


def _normalize_phone(phone: str) -> str:
    digits = "".join(c for c in phone if c.isdigit())
    if len(digits) == 10:
        return f"+1{digits}"
    if len(digits) == 11 and digits.startswith("1"):
        return f"+{digits}"
    return f"+{digits}"


def _get_api() -> Optional[PyiCloudService]:
    global _api
    if _api:
        return _api
    if not APPLE_ID or not APPLE_PASSWORD:
        print("⚠️  Find My: APPLE_ID or APPLE_PASSWORD not set in .env")
        return None
    try:
        print(f"🍎 Signing into iCloud as {APPLE_ID}...")
        _api = PyiCloudService(APPLE_ID, APPLE_PASSWORD)
        if _api.requires_2fa:
            print("🔐 2FA required. Check your Apple device for the code.")
            code = input("Enter 2FA code: ").strip()
            if not _api.validate_2fa_code(code):
                print("❌ Invalid 2FA code")
                _api = None
                return None
        print("✅ iCloud signed in successfully")
        return _api
    except PyiCloudFailedLoginException as e:
        print(f"❌ iCloud login failed: {e}")
        return None
    except Exception as e:
        print(f"❌ iCloud error: {e}")
        return None


def poll_once() -> None:
    api = _get_api()
    if not api:
        return
    try:
        friends = api.friends.all()
    except Exception as e:
        print(f"📍 Find My poll error: {e}")
        return

    registered = {u["phone"]: u for u in db.get_all_users()}

    for friend in friends:
        loc = friend.get("location")
        if not loc or not loc.get("latitude") or not loc.get("longitude"):
            continue

        lat = loc["latitude"]
        lng = loc["longitude"]
        name = f"{friend.get('firstName', '')} {friend.get('lastName', '')}".strip()

        # Try to match by phone number
        matched_phone = None
        for phone_entry in friend.get("phones", []):
            raw = phone_entry.get("number", "")
            normalized = _normalize_phone(raw)
            if normalized in registered:
                matched_phone = normalized
                break

        # Fall back to matching by stored findmy_name
        if not matched_phone:
            for phone, user in registered.items():
                if user.get("findmy_name") and user["findmy_name"].lower() == name.lower():
                    matched_phone = phone
                    break

        if matched_phone:
            db.upsert_user(matched_phone, current_lat=lat, current_lng=lng)
            print(f"📍 Updated location for {matched_phone} ({name}): {lat:.4f}, {lng:.4f}")
        else:
            print(f"📍 Find My: {name} @ {lat:.4f}, {lng:.4f} — no matching registered user")


def _loop() -> None:
    while True:
        try:
            poll_once()
        except Exception as e:
            print(f"📍 Find My loop error: {e}")
        time.sleep(POLL_INTERVAL)


def start() -> None:
    if not APPLE_ID or not APPLE_PASSWORD:
        print("⚠️  Find My disabled: set APPLE_ID and APPLE_PASSWORD in .env")
        return
    # Initial login (may prompt for 2FA)
    _get_api()
    threading.Thread(target=_loop, daemon=True).start()
    print(f"📍 Find My polling started (every {POLL_INTERVAL // 60} min)")
