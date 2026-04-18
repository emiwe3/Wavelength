import os
import queue
import sqlite3
import tempfile
import threading
import time
import requests
import subprocess
from pathlib import Path

DB_PATH = Path.home() / "Library/Messages/chat.db"
BACKEND_URL = "http://localhost:8000"
POLL_INTERVAL = 0.5

_sender_queues: dict = {}
_sender_queues_lock = threading.Lock()


def get_connection():
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def get_latest_rowid(conn):
    row = conn.execute(
        "SELECT MAX(ROWID) as max_id FROM message WHERE is_from_me = 0"
    ).fetchone()
    return row["max_id"] or 0


def get_new_messages(conn, since_rowid):
    return conn.execute("""
        SELECT m.ROWID, m.text, m.is_from_me, m.date,
               h.id as sender, c.chat_identifier
        FROM message m
        LEFT JOIN handle h ON m.handle_id = h.ROWID
        LEFT JOIN chat_message_join cmj ON m.ROWID = cmj.message_id
        LEFT JOIN chat c ON cmj.chat_id = c.ROWID
        WHERE m.ROWID > ?
          AND m.is_from_me = 0
          AND m.text IS NOT NULL
          AND m.text != ''
        ORDER BY m.ROWID ASC
    """, (since_rowid,)).fetchall()


def send_reply(sender, reply_text):
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        f.write(reply_text)
        tmp_path = f.name
    try:
        script = f"""
set msgText to (do shell script "cat " & quoted form of "{tmp_path}")
tell application "Messages"
    set myService to first service whose service type = iMessage
    set myBuddy to buddy "{sender}" of myService
    send msgText to myBuddy
end tell
"""
        subprocess.run(["osascript", "-e", script], check=True)
    finally:
        os.unlink(tmp_path)


def sender_worker(sender, q):
    while True:
        item = q.get()
        if item is None:
            break
        text, chat_guid = item
        try:
            res = requests.post(f"{BACKEND_URL}/api/bot/message", json={
                "phone": sender,
                "chat_guid": chat_guid or sender,
                "text": text,
            }, timeout=90)
            data = res.json()
            if data.get("reply"):
                send_reply(sender, data["reply"])
                print(f"Replied to {sender}: {data['reply'][:80]}")
        except Exception as e:
            print(f"Error handling message from {sender}: {e}")


def enqueue_message(sender, text, chat_guid):
    with _sender_queues_lock:
        if sender not in _sender_queues:
            q = queue.Queue()
            _sender_queues[sender] = q
            t = threading.Thread(target=sender_worker, args=(sender, q), daemon=True)
            t.start()
        _sender_queues[sender].put((text, chat_guid))


def main():
    print("iMessage bridge starting...")
    conn = get_connection()
    last_rowid = get_latest_rowid(conn)
    conn.close()
    print(f"Watching for new messages (last ROWID: {last_rowid})...")

    while True:
        try:
            conn = get_connection()
            new_msgs = get_new_messages(conn, last_rowid)
            conn.close()

            for msg in new_msgs:
                last_rowid = max(last_rowid, msg["ROWID"])
                sender = msg["sender"]
                text = msg["text"]
                if not sender or not text:
                    continue

                print(f"From {sender}: {text}")
                enqueue_message(sender, text, msg["chat_identifier"])

        except Exception as e:
            print(f"DB error: {e}")

        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
