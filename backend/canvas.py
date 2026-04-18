"""
canvas.py — fetch upcoming assignments from the Canvas LMS REST API.
"""

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

import httpx


def get_upcoming_assignments(
    canvas_token: str,
    canvas_domain: str,
    days_ahead: int = 21,
) -> List[Dict[str, Any]]:
    """
    Returns assignments due within the next `days_ahead` days, sorted by due date.
    Each dict: name, course, due_at (ISO str), points, submitted (bool).
    """
    headers = {"Authorization": f"Bearer {canvas_token}"}
    base = f"https://{canvas_domain}/api/v1"
    now = datetime.now(timezone.utc)
    cutoff = now + timedelta(days=days_ahead)

    with httpx.Client(timeout=10) as client:
        resp = client.get(
            f"{base}/courses?enrollment_state=active&per_page=50",
            headers=headers,
        )
        resp.raise_for_status()
        courses = resp.json()

        assignments: List[Dict[str, Any]] = []
        for course in courses:
            if not isinstance(course, dict) or not course.get("id"):
                continue
            try:
                r = client.get(
                    f"{base}/courses/{course['id']}/assignments"
                    "?per_page=50&order_by=due_at&include[]=submission",
                    headers=headers,
                )
                if r.status_code != 200:
                    continue
                for a in r.json():
                    if not a.get("due_at"):
                        continue
                    due = datetime.fromisoformat(a["due_at"].replace("Z", "+00:00"))
                    if due < now or due > cutoff:
                        continue
                    sub = a.get("submission") or {}
                    assignments.append({
                        "name": a["name"],
                        "course": course.get("name", "Unknown Course"),
                        "due_at": a["due_at"],
                        "points": a.get("points_possible", 0),
                        "submitted": bool(sub.get("submitted_at")),
                    })
            except Exception:
                continue

    assignments.sort(key=lambda a: a["due_at"])
    return assignments
