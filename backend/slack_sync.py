from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError


def get_announcements(slack_token: str, channel_id: str = None, hours: int = 48) -> List[Dict[str, Any]]:
    client = WebClient(token=slack_token)
    oldest = str((datetime.now(timezone.utc) - timedelta(hours=hours)).timestamp())

    channels = []
    cursor = None
    while True:
        try:
            resp = client.conversations_list(
                types="public_channel",
                exclude_archived=True,
                limit=200,
                cursor=cursor,
            )
        except SlackApiError as exc:
            raise RuntimeError(f"Slack API error listing channels: {exc.response['error']}")

        for ch in resp.get("channels", []):
            if ch.get("is_member"):
                channels.append({"id": ch["id"], "name": ch.get("name", ch["id"])})

        cursor = resp.get("response_metadata", {}).get("next_cursor")
        if not cursor:
            break

    messages: List[Dict[str, Any]] = []
    for ch in channels:
        try:
            result = client.conversations_history(channel=ch["id"], oldest=oldest, limit=200)
            for m in result.get("messages", []):
                text = m.get("text", "").strip()
                if text:
                    messages.append({
                        "channel": ch["name"],
                        "text": text,
                        "ts": m.get("ts", ""),
                    })
        except SlackApiError:
            continue

    messages.sort(key=lambda m: m["ts"], reverse=True)
    return messages
