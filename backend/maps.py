"""
maps.py — Google Routes API for travel time estimates.
"""


import os
import httpx
from datetime import datetime, timedelta, timezone


MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY")
ROUTES_URL = "https://routes.googleapis.com/directions/v2:computeRoutes"


MODE_MAP = {
   "walking": "WALK",
   "driving": "DRIVE",
   "transit": "TRANSIT",
   "bicycling": "BICYCLE",
}

def _compute_route(origin_lat: float, origin_lng: float, destination: str, mode: str) -> dict:
   travel_mode = MODE_MAP.get(mode, "WALK")
   with httpx.Client(timeout=5) as client:
       resp = client.post(
           ROUTES_URL,
           headers={
               "X-Goog-Api-Key": MAPS_API_KEY,
               "X-Goog-FieldMask": "routes.duration,routes.distanceMeters",
           },
           json={
               "origin": {"location": {"latLng": {"latitude": origin_lat, "longitude": origin_lng}}},
               "destination": {"address": destination},
               "travelMode": travel_mode,
           },
       )
   data = resp.json()
   routes = data.get("routes", [])
   if not routes:
       return {}
   return routes[0]




def get_travel_time(origin_lat: float, origin_lng: float, destination: str, mode: str = "walking") -> str:
   if not MAPS_API_KEY:
       return ""
   try:
       route = _compute_route(origin_lat, origin_lng, destination, mode)
       if not route:
           return ""
       raw = route.get("duration", "")
       seconds = int(raw.rstrip("s")) if raw else 0
       minutes = round(seconds / 60)
       return f"{minutes} min {mode}"
   except Exception:
       return ""




def get_leave_by(origin_lat: float, origin_lng: float, destination: str,
                event_start_iso: str, mode: str = "walking") -> dict:
   if not MAPS_API_KEY:
       return {}
   try:
       route = _compute_route(origin_lat, origin_lng, destination, mode)
       if not route:
           return {}


       raw = route.get("duration", "")
       duration_seconds = int(raw.rstrip("s")) if raw else 0
       minutes = round(duration_seconds / 60)


       event_dt = datetime.fromisoformat(event_start_iso)
       if event_dt.tzinfo is None:
           event_dt = event_dt.replace(tzinfo=timezone.utc)
       leave_dt = event_dt - timedelta(seconds=duration_seconds)
       leave_by = leave_dt.strftime("%-I:%M %p")


       return {
           "travel_time": f"{minutes} min {mode}",
           "leave_by": leave_by,
       }
   except Exception:
       return {}