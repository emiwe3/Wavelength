import urllib.request
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List

from icalendar import Calendar


def fetch_events(ical_url: str, days_ahead: int = 21) -> List[Dict[str, Any]]:
    with urllib.request.urlopen(ical_url, timeout=10) as resp:
        data = resp.read()

    cal = Calendar.from_ical(data)
    now = datetime.now(timezone.utc)
    cutoff = now + timedelta(days=days_ahead)

    events: List[Dict[str, Any]] = []
    for component in cal.walk():
        if component.name != "VEVENT":
            continue

        dtstart = component.get("DTSTART")
        if dtstart is None:
            continue

        start_dt = _to_datetime(dtstart.dt)
        if start_dt < now or start_dt > cutoff:
            continue

        event: Dict[str, Any] = {
            "title": str(component.get("SUMMARY", "Untitled")),
            "start": start_dt.isoformat(),
        }

        dtend = component.get("DTEND")
        if dtend is not None:
            event["end"] = _to_datetime(dtend.dt).isoformat()

        location = component.get("LOCATION")
        if location:
            event["location"] = str(location)

        events.append(event)

    events.sort(key=lambda e: e["start"])
    return events


def _to_datetime(dt) -> datetime:
    if isinstance(dt, date) and not isinstance(dt, datetime):
        dt = datetime(dt.year, dt.month, dt.day, tzinfo=timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt
