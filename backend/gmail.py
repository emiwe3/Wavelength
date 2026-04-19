import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]

_ACADEMIC_KEYWORDS = [
    ".edu",
    "registrar",
    "financial aid",
    "bursar",
    "dean",
    "provost",
    "professor",
    "advising",
    "academic",
    "department",
    "university",
    "college",
    "faculty",
    "admin",
]

REDIRECT_URI = os.getenv("GOOGLE_OAUTH_REDIRECT_URI", "http://localhost:8080/oauth/callback")


def _client_config() -> Dict:
    return {
        "web": {
            "client_id": os.environ["GOOGLE_CLIENT_ID"],
            "client_secret": os.environ["GOOGLE_CLIENT_SECRET"],
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
        }
    }


def get_oauth_url() -> str:
    flow = Flow.from_client_config(_client_config(), scopes=SCOPES, redirect_uri=REDIRECT_URI)
    url, _ = flow.authorization_url(
        access_type="offline",
        prompt="consent",
        include_granted_scopes="true",
    )
    return url


def exchange_code(code: str) -> Dict[str, Any]:
    flow = Flow.from_client_config(_client_config(), scopes=SCOPES, redirect_uri=REDIRECT_URI)
    flow.fetch_token(code=code)
    return _creds_to_dict(flow.credentials)


def get_academic_emails(
    credentials_dict: Dict[str, Any],
    hours: int = 48,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    creds = _dict_to_creds(credentials_dict)

    if creds.expired and creds.refresh_token:
        creds.refresh(Request())

    service = build("gmail", "v1", credentials=creds)

    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    after_epoch = int(since.timestamp())

    result = (
        service.users()
        .messages()
        .list(userId="me", q=f"is:unread after:{after_epoch}", maxResults=50)
        .execute()
    )

    messages = result.get("messages", [])
    emails: List[Dict[str, Any]] = []

    for msg_ref in messages:
        msg = (
            service.users()
            .messages()
            .get(
                userId="me",
                id=msg_ref["id"],
                format="metadata",
                metadataHeaders=["From", "Subject", "Date"],
            )
            .execute()
        )

        headers = {h["name"]: h["value"] for h in msg["payload"]["headers"]}
        from_header = headers.get("From", "")

        if not _is_academic_sender(from_header):
            continue

        emails.append({
            "id": msg_ref["id"],
            "from": from_header,
            "subject": headers.get("Subject", "(no subject)"),
            "date": headers.get("Date", ""),
            "preview": msg.get("snippet", ""),
        })

    return emails, _creds_to_dict(creds)


def _is_academic_sender(from_header: str) -> bool:
    lower = from_header.lower()
    return any(kw in lower for kw in _ACADEMIC_KEYWORDS)


def _creds_to_dict(creds: Credentials) -> Dict[str, Any]:
    return {
        "token": creds.token,
        "refresh_token": creds.refresh_token,
        "token_uri": creds.token_uri,
        "client_id": creds.client_id,
        "client_secret": creds.client_secret,
        "scopes": list(creds.scopes) if creds.scopes else list(SCOPES),
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


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    print(get_oauth_url())
