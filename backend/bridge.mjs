import { IMessageSDK } from "@photon-ai/imessage-kit";
import Database from "better-sqlite3";
import os from "os";
import path from "path";
import fs from "fs";
import { execSync } from "child_process";

const BACKEND_URL = process.env.BACKEND_URL || "http://localhost:8000";
const POLL_MS = 500;
const DB_PATH = path.join(os.homedir(), "Library/Messages/chat.db");

const sdk = new IMessageSDK();
const db = new Database(DB_PATH, { readonly: true });

const attachmentStmt = db.prepare(`
  SELECT a.filename, a.mime_type
  FROM attachment a
  JOIN message_attachment_join maj ON a.ROWID = maj.attachment_id
  WHERE maj.message_id = ?
    AND (a.mime_type LIKE 'image/%'
      OR a.mime_type LIKE 'audio/%'
      OR a.mime_type = 'com.apple.coreaudio-format'
      OR a.filename LIKE '%.caf'
      OR a.transfer_name LIKE '%.caf')
  LIMIT 1
`);

const chatGuidStmt = db.prepare(`
  SELECT chat.guid FROM chat
  JOIN chat_message_join ON chat.ROWID = chat_message_join.chat_id
  WHERE chat_message_join.message_id = ?
  LIMIT 1
`);

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
      AND message.item_type = 0
      AND (message.text IS NOT NULL OR message.cache_has_attachments = 1)
    ORDER BY message.ROWID ASC
  `).all(lastRowId);

  for (const row of rows) {
    lastRowId = row.ROWID;
    const text = row.text?.trim() || "";
    const sender = row.sender;
    if (!sender) continue;

    let image_base64 = null;
    let image_media_type = null;
    let audio_path = null;
    const attachment = attachmentStmt.get(row.ROWID);
    if (attachment) {
      const filePath = attachment.filename.replace("~", os.homedir());
      const isAudio = attachment.mime_type?.startsWith("audio/") || attachment.mime_type === "com.apple.coreaudio-format" || attachment.filename?.endsWith(".caf");
      if (isAudio) {
        audio_path = filePath;
        console.log(`🎙️  Audio from ${sender}: ${filePath}`);
      } else {
        try {
          image_base64 = fs.readFileSync(filePath).toString("base64");
          image_media_type = attachment.mime_type;
          console.log(`🖼️  Image from ${sender}: ${filePath}`);
        } catch (e) {
          console.error(`❌ Could not read attachment: ${e.message}`);
        }
      }
    }

    if (!text && !image_base64 && !audio_path) continue;

    const chatRow = chatGuidStmt.get(row.ROWID);
    const chat_guid = chatRow?.guid || sender;

    console.log(`📩 From ${sender}: ${text || (audio_path ? "(voice)" : "(image only)")}`);

    try {
      const res = await fetch(`${BACKEND_URL}/api/bot/message`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ phone: sender, text, image_base64, image_media_type, audio_path, chat_guid }),
      });
      const data = await res.json();
      if (data.reply) {
        await sdk.send(sender, data.reply);
        console.log(`📤 Replied: ${data.reply.slice(0, 80)}`);
      }
      if (data.audio_reply) {
        const { path: audioFile, recipient } = data.audio_reply;
        try {
          execSync(`osascript -e 'tell application "Messages" to send POSIX file "${audioFile}" to buddy "${recipient}" of service "iMessage"'`);
          console.log(`🔊 Sent audio reply to ${recipient}`);
        } catch (e) {
          console.error(`❌ Audio send failed: ${e.message}`);
        }
      }
      if (data.scheduled_message) {
        const { recipient, text: msgText, scheduled_for } = data.scheduled_message;
        const tzAware = /[Z+\-]\d{2}:?\d{2}$/.test(scheduled_for) ? scheduled_for : `${scheduled_for}-04:00`;
        const sendAt = new Date(tzAware).getTime();
        const delay = Math.max(0, sendAt - Date.now());
        console.log(`⏰ Scheduling message to ${recipient} in ${Math.round(delay / 1000)}s: "${msgText}"`);
        setTimeout(async () => {
          try {
            await sdk.send(recipient, msgText);
            console.log(`📤 Sent scheduled message to ${recipient}: "${msgText}"`);
          } catch (e) {
            console.error(`❌ Scheduled send failed: ${e.message}`);
          }
        }, delay);
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
