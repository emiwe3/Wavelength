import json
import sqlite3
from pathlib import Path
from typing import Any, Dict, Optional

DB_PATH = Path(__file__).parent / "users.db"


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with _connect() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                phone             TEXT PRIMARY KEY,
                canvas_token      TEXT,
                canvas_domain     TEXT,
                ical_url          TEXT,
                gmail_credentials TEXT,
                slack_token       TEXT,
                slack_channel     TEXT,
                onboarding_step   TEXT DEFAULT 'start',
                preferences       TEXT DEFAULT '{}'
            )
        """)
        # Migrate existing tables by adding any missing columns
        existing = {row[1] for row in conn.execute("PRAGMA table_info(users)")}
        migrations = {
            "canvas_domain": "TEXT",
            "ical_url": "TEXT",
            "gmail_credentials": "TEXT",
            "slack_channel": "TEXT",
            "onboarding_step": "TEXT DEFAULT 'start'",
            "preferences": "TEXT DEFAULT '{}'",
        }
        migrations["slack_workspaces"] = "TEXT DEFAULT '[]'"
        for col, col_def in migrations.items():
            if col not in existing:
                conn.execute(f"ALTER TABLE users ADD COLUMN {col} {col_def}")
        conn.commit()


def get_user(phone: str) -> Optional[Dict[str, Any]]:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM users WHERE phone = ?", (phone,)).fetchone()
    if row is None:
        return None
    user = dict(row)
    if user.get("gmail_credentials"):
        user["gmail_credentials"] = json.loads(user["gmail_credentials"])
    if user.get("preferences"):
        user["preferences"] = json.loads(user["preferences"])
    return user


def upsert_user(phone: str, **fields) -> None:
    if "gmail_credentials" in fields and isinstance(fields["gmail_credentials"], dict):
        fields["gmail_credentials"] = json.dumps(fields["gmail_credentials"])
    if "preferences" in fields and isinstance(fields["preferences"], dict):
        fields["preferences"] = json.dumps(fields["preferences"])

    with _connect() as conn:
        existing = conn.execute(
            "SELECT phone FROM users WHERE phone = ?", (phone,)
        ).fetchone()

        if existing is None:
            fields["phone"] = phone
            cols = ", ".join(fields.keys())
            placeholders = ", ".join("?" * len(fields))
            conn.execute(
                f"INSERT INTO users ({cols}) VALUES ({placeholders})",
                list(fields.values()),
            )
        else:
            if fields:
                sets = ", ".join(f"{k} = ?" for k in fields)
                conn.execute(
                    f"UPDATE users SET {sets} WHERE phone = ?",
                    [*fields.values(), phone],
                )
        conn.commit()


def get_preference(phone: str, key: str, default=None):
    user = get_user(phone)
    if not user:
        return default
    return user.get("preferences", {}).get(key, default)


def set_preference(phone: str, key: str, value) -> None:
    user = get_user(phone)
    prefs = user.get("preferences", {}) if user else {}
    prefs[key] = value
    upsert_user(phone, preferences=prefs)


def get_slack_workspaces(phone: str) -> list:
    with _connect() as conn:
        row = conn.execute(
            "SELECT slack_workspaces FROM users WHERE phone = ?", (phone,)
        ).fetchone()
    if not row or not row[0]:
        return []
    try:
        return json.loads(row[0])
    except Exception:
        return []


def add_slack_workspace(phone: str, token: str, team_id: str, team_name: str) -> None:
    workspaces = get_slack_workspaces(phone)
    workspaces = [w for w in workspaces if w.get("team_id") != team_id]
    workspaces.append({"token": token, "team_id": team_id, "team_name": team_name})
    upsert_user(phone, slack_workspaces=json.dumps(workspaces))