"""
maps.py — Google Maps Distance Matrix for travel time estimates.
"""

import os
import httpx

MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY")
MAPS_URL = "https://maps.googleapis.com/maps/api/distancematrix/json"

MODES = {"walking", "driving", "transit", "bicycling"}


def get_travel_time(origin_lat: float, origin_lng: float, destination: str, mode: str = "walking") -> str:
    """
    Returns a human-readable travel time string like '12 mins walking'
    or an empty string if the lookup fails.
    """
    if not MAPS_API_KEY:
        return ""
    if mode not in MODES:
        mode = "walking"

    try:
        with httpx.Client(timeout=5) as client:
            resp = client.get(MAPS_URL, params={
                "origins": f"{origin_lat},{origin_lng}",
                "destinations": destination,
                "mode": mode,
                "key": MAPS_API_KEY,
            })
        data = resp.json()
        element = data["rows"][0]["elements"][0]
        if element["status"] != "OK":
            return ""
        duration = element["duration"]["text"]
        return f"{duration} {mode}"
    except Exception:
        return ""


def get_leave_by(origin_lat: float, origin_lng: float, destination: str,
                 event_start_iso: str, mode: str = "walking") -> dict:
    """
    Returns dict with travel_time string and leave_by time string.
    e.g. {"travel_time": "12 mins walking", "leave_by": "6:48 PM"}
    """
    if not MAPS_API_KEY:
        return {}

    try:
        with httpx.Client(timeout=5) as client:
            resp = client.get(MAPS_URL, params={
                "origins": f"{origin_lat},{origin_lng}",
                "destinations": destination,
                "mode": mode,
                "key": MAPS_API_KEY,
            })
        data = resp.json()
        element = data["rows"][0]["elements"][0]
        if element["status"] != "OK":
            return {}

        duration_seconds = element["duration"]["value"]
        duration_text = element["duration"]["text"]

        from datetime import datetime, timedelta, timezone
        event_dt = datetime.fromisoformat(event_start_iso)
        if event_dt.tzinfo is None:
            event_dt = event_dt.replace(tzinfo=timezone.utc)
        leave_dt = event_dt - timedelta(seconds=duration_seconds)
        leave_by = leave_dt.strftime("%-I:%M %p")

        return {
            "travel_time": f"{duration_text} {mode}",
            "leave_by": leave_by,
        }
    except Exception:
        return {}
