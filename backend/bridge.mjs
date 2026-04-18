import { IMessageSDK } from "@photon-ai/imessage-kit";
import Database from "better-sqlite3";
import os from "os";
import path from "path";

const BACKEND_URL = process.env.BACKEND_URL || "http://localhost:8000";
const POLL_MS = 500;
const DB_PATH = path.join(os.homedir(), "Library/Messages/chat.db");

const sdk = new IMessageSDK();
const db = new Database(DB_PATH, { readonly: true });

// Start from the current max ROWID so we only process new messages
let lastRowId = db.prepare("SELECT MAX(ROWID) as m FROM message").get().m ?? 0;
console.log(`🌉 iMessage bridge starting (last ROWID: ${lastRowId})...`);

async function poll() {
  const rows = db.prepare(`
    SELECT message.ROWID, message.text, handle.id as sender
    FROM message
    LEFT JOIN handle ON message.handle_id = handle.ROWID
    WHERE message.ROWID > ?
      AND message.is_from_me = 0
      AND message.text IS NOT NULL
      AND message.item_type = 0
    ORDER BY message.ROWID ASC
  `).all(lastRowId);

  for (const row of rows) {
    lastRowId = row.ROWID;
    const text = row.text?.trim();
    const sender = row.sender;
    if (!text || !sender) continue;

    console.log(`📩 From ${sender}: ${text}`);

    try {
      const res = await fetch(`${BACKEND_URL}/api/bot/message`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ phone: sender, text }),
      });
      const data = await res.json();
      if (data.reply) {
        await sdk.send(sender, data.reply);
        console.log(`📤 Replied: ${data.reply.slice(0, 80)}`);
      }
    } catch (err) {
      console.error("❌ Error:", err.message);
    }
  }
}

let busy = false;

async function safePoll() {
  if (busy) return;
  busy = true;
  try { await poll(); } finally { busy = false; }
}

console.log(`✅ Polling for new iMessages every ${POLL_MS / 1000}s...`);
setInterval(safePoll, POLL_MS);
