import json, os, sqlite3
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

import agent, context as ctx_mod

db_path = Path(__file__).parent / "users.db"
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row
row = conn.execute("SELECT * FROM users WHERE phone = '+14156056081'").fetchone()
conn.close()

user = dict(row)
if user.get("gmail_credentials") and isinstance(user["gmail_credentials"], str):
    user["gmail_credentials"] = json.loads(user["gmail_credentials"])

print("PulsePoint is ready. Type your message (Ctrl+C to quit).\n")

while True:
    try:
        msg = input("You: ").strip()
        if not msg:
            continue
        reply = agent.reply(user, msg)
        print(f"\nPulsePoint: {reply}\n")
    except KeyboardInterrupt:
        print("\nBye!")
        break
