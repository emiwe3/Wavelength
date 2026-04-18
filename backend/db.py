import sqlite3

DB_PATH = "users.db"


def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            phone TEXT PRIMARY KEY,
            google_access_token TEXT,
            google_refresh_token TEXT,
            canvas_token TEXT,
            canvas_domain TEXT,
            slack_token TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()


def get_user(phone: str):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM users WHERE phone = ?", (phone,)).fetchone()
    conn.close()
    return dict(row) if row else None


def upsert_user(phone: str, **fields):
    conn = sqlite3.connect(DB_PATH)
    existing = conn.execute("SELECT phone FROM users WHERE phone = ?", (phone,)).fetchone()
    if not existing:
        conn.execute("INSERT INTO users (phone) VALUES (?)", (phone,))
    if fields:
        set_clause = ", ".join(f"{k} = ?" for k in fields)
        conn.execute(f"UPDATE users SET {set_clause} WHERE phone = ?", (*fields.values(), phone))
    conn.commit()
    conn.close()
