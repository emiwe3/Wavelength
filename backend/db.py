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
        conn.execute("""
            CREATE TABLE IF NOT EXISTS context_cache (
                phone      TEXT PRIMARY KEY,
                context    TEXT NOT NULL,
                updated_at REAL NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS slack_workspaces (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                phone     TEXT NOT NULL,
                token     TEXT NOT NULL,
                team_id   TEXT NOT NULL,
                team_name TEXT NOT NULL
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
            "reminders_sent": "TEXT DEFAULT '{}'",
            "findmy_id": "TEXT",
            "findmy_name": "TEXT",
        }
        migrations["slack_workspaces"] = "TEXT DEFAULT '[]'"
        migrations["current_lat"] = "REAL"
        migrations["current_lng"] = "REAL"
        for col, col_def in migrations.items():
            if col not in existing:
                conn.execute(f"ALTER TABLE users ADD COLUMN {col} {col_def}")
        conn.commit()


def get_all_users() -> list:
    with _connect() as conn:
        rows = conn.execute("SELECT * FROM users").fetchall()
    users = []
    for row in rows:
        user = dict(row)
        if user.get("gmail_credentials"):
            user["gmail_credentials"] = json.loads(user["gmail_credentials"])
        if user.get("preferences"):
            user["preferences"] = json.loads(user["preferences"])
        if user.get("reminders_sent"):
            user["reminders_sent"] = json.loads(user["reminders_sent"])
        users.append(user)
    return users


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
    if "reminders_sent" in fields and isinstance(fields["reminders_sent"], dict):
        fields["reminders_sent"] = json.dumps(fields["reminders_sent"])

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


def get_cached_context(phone: str, ttl: float = 300) -> Optional[str]:
    import time
    with _connect() as conn:
        row = conn.execute(
            "SELECT context, updated_at FROM context_cache WHERE phone = ?", (phone,)
        ).fetchone()
    if row and (time.time() - row["updated_at"]) < ttl:
        return row["context"]
    return None


def set_cached_context(phone: str, context: str) -> None:
    import time
    with _connect() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO context_cache (phone, context, updated_at) VALUES (?, ?, ?)",
            (phone, context, time.time()),
        )
        conn.commit()


def set_preference(phone: str, key: str, value) -> None:
    user = get_user(phone)
    prefs = user.get("preferences", {}) if user else {}
    prefs[key] = value
    upsert_user(phone, preferences=prefs)


def get_slack_workspaces(phone: str) -> list:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT token, team_id, team_name FROM slack_workspaces WHERE phone = ?", (phone,)
        ).fetchall()
    return [dict(row) for row in rows]


def add_slack_workspace(phone: str, token: str, team_id: str, team_name: str) -> None:
    with _connect() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO slack_workspaces (phone, token, team_id, team_name) VALUES (?, ?, ?, ?)",
            (phone, token, team_id, team_name),
        )
        conn.commit()