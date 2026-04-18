from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build


def create_event(
    credentials_dict: Dict[str, Any],
    title: str,
    date: str,
    start_time: str,
    end_time: Optional[str] = None,
    description: str = "",
    timezone: str = "America/New_York",
) -> Dict[str, Any]:
    creds = _dict_to_creds(credentials_dict)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())

    service = build("calendar", "v3", credentials=creds)

    start_dt = f"{date}T{start_time}:00"
    if end_time:
        end_dt = f"{date}T{end_time}:00"
    else:
        end_dt = (datetime.fromisoformat(start_dt) + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%S")

    event = service.events().insert(
        calendarId="primary",
        body={
            "summary": title,
            "description": description,
            "start": {"dateTime": start_dt, "timeZone": timezone},
            "end": {"dateTime": end_dt, "timeZone": timezone},
        },
    ).execute()

    return {
        "title": event["summary"],
        "start": event["start"]["dateTime"],
        "end": event["end"]["dateTime"],
        "link": event.get("htmlLink", ""),
    }


def _dict_to_creds(d: Dict[str, Any]) -> Credentials:
    return Credentials(
        token=d["token"],
        refresh_token=d["refresh_token"],
        token_uri=d["token_uri"],
        client_id=d["client_id"],
        client_secret=d["client_secret"],
        scopes=d["scopes"],
    )
