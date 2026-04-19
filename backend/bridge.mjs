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
      OR a.mime_type = 'application/pdf'
      OR a.mime_type = 'com.adobe.pdf'
      OR a.mime_type = 'image/heic'
      OR a.mime_type = 'image/heif'
      OR a.filename LIKE '%.caf'
      OR a.filename LIKE '%.pdf'
      OR a.filename LIKE '%.heic'
      OR a.filename LIKE '%.heif'
      OR a.transfer_name LIKE '%.caf'
      OR a.transfer_name LIKE '%.pdf')
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

// Parse lat/lng from Apple Maps or Google Maps URLs shared via iMessage
function extractLocation(text) {
  const appleMaps = text.match(/maps\.apple\.com\/\?.*ll=([-\d.]+),([-\d.]+)/);
  if (appleMaps) return { lat: parseFloat(appleMaps[1]), lng: parseFloat(appleMaps[2]) };
  const googleMaps = text.match(/maps\.google\.com\/\?.*q=([-\d.]+),([-\d.]+)/);
  if (googleMaps) return { lat: parseFloat(googleMaps[1]), lng: parseFloat(googleMaps[2]) };
  return null;
}

// Parse raw coordinates e.g. "my location is 40.357, -74.667"
function extractCoords(text) {
  const m = text.match(/([-]?\d{1,3}\.\d+)[,\s]+([-]?\d{1,3}\.\d+)/);
  if (m) return { lat: parseFloat(m[1]), lng: parseFloat(m[2]) };
  return null;
}

async function poll() {
  const rows = db.prepare(`
    SELECT message.ROWID, message.text, handle.id as sender,
           attachment.filename, attachment.uti
    FROM message
    LEFT JOIN handle ON message.handle_id = handle.ROWID
    LEFT JOIN message_attachment_join ON message.ROWID = message_attachment_join.message_id
    LEFT JOIN attachment ON message_attachment_join.attachment_id = attachment.ROWID
    WHERE message.ROWID > ?
      AND message.is_from_me = 0
      AND message.item_type = 0
      AND (message.text IS NOT NULL OR message.cache_has_attachments = 1)
    ORDER BY message.ROWID ASC
  `).all(lastRowId);

  const seen = new Set();
  for (const row of rows) {
    if (seen.has(row.ROWID)) continue;
    seen.add(row.ROWID);
    lastRowId = Math.max(lastRowId, row.ROWID);

    const sender = row.sender;
    if (!sender) continue;

    // Handle iMessage "Send Current Location" (.mapitem attachment)
    if (row.uti === "com.apple.mapkit.map-item" && row.filename) {
      try {
        const filepath = row.filename.replace("~", os.homedir());
        const out = execSync(`plutil -p "${filepath}"`, { encoding: "utf8" });
        const latMatch = out.match(/"latitude"[^=]+=>\s*([-\d.]+)/i);
        const lngMatch = out.match(/"longitude"[^=]+=>\s*([-\d.]+)/i);
        if (latMatch && lngMatch) {
          const lat = parseFloat(latMatch[1]);
          const lng = parseFloat(lngMatch[1]);
          console.log(`📍 Location received from ${sender}: lat=${lat}, lng=${lng}`);
          await fetch(`${BACKEND_URL}/api/location`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ phone: sender, lat, lng }),
          }).catch(() => {});
          await sdk.send(sender, "Got your location! I'll use it for travel times.");
        }
      } catch (e) {
        console.error("📍 Failed to parse mapitem:", e.message);
      }
      continue;
    }

    const text = row.text?.trim() || "";

    // Check if message contains a maps URL or raw coordinates
    if (text) {
      const loc = extractLocation(text) ?? extractCoords(text);
      if (loc) {
        console.log(`📍 Location from ${sender}: ${loc.lat}, ${loc.lng}`);
        await fetch(`${BACKEND_URL}/api/location`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ phone: sender, lat: loc.lat, lng: loc.lng }),
        }).catch(() => {});
        await sdk.send(sender, "Got your location! I'll use it for travel times.");
        continue;
      }

      // Allow user to link their Find My name: "link findmy [name]"
      const linkMatch = text.match(/^link findmy\s+(.+)/i);
      if (linkMatch) {
        const findmy_name = linkMatch[1].trim();
        await fetch(`${BACKEND_URL}/api/location/link`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ phone: sender, findmy_name }),
        }).catch(() => {});
        await sdk.send(sender, `Got it! I've linked your Find My name "${findmy_name}" to your number. Your location will update automatically.`);
        continue;
      }
    }

    let image_base64 = null;
    let image_media_type = null;
    let audio_path = null;
    const attachment = attachmentStmt.get(row.ROWID);
    if (attachment) {
      const filePath = attachment.filename.replace("~", os.homedir());
      const mime = attachment.mime_type || "";
      const isAudio = mime.startsWith("audio/") || mime === "com.apple.coreaudio-format" || filePath.endsWith(".caf");
      const isPdf = mime === "application/pdf" || mime === "com.adobe.pdf" || filePath.endsWith(".pdf");
      const isHeic = mime === "image/heic" || mime === "image/heif" || filePath.endsWith(".heic") || filePath.endsWith(".heif");
      const needsConvert = isPdf || isHeic;

      if (isAudio) {
        audio_path = filePath;
        console.log(`🎙️  Audio from ${sender}: ${filePath}`);
      } else if (needsConvert) {
        try {
          const jpgPath = `/tmp/attachment_${Date.now()}.jpg`;
          execSync(`sips -s format jpeg -Z 1600 "${filePath}" --out "${jpgPath}"`, { stdio: "pipe" });
          if (fs.existsSync(jpgPath)) {
            image_base64 = fs.readFileSync(jpgPath).toString("base64");
            image_media_type = "image/jpeg";
            fs.unlinkSync(jpgPath);
            console.log(`🔄 ${isPdf ? "PDF" : "HEIC"}→JPEG from ${sender}: ${filePath}`);
          } else {
            console.error(`❌ sips conversion produced no output: ${filePath}`);
          }
        } catch (e) {
          console.error(`❌ Conversion failed: ${e.message}`);
        }
      } else if (mime.startsWith("image/")) {
        try {
          const jpgPath = `/tmp/attachment_${Date.now()}.jpg`;
          execSync(`sips -s format jpeg -Z 1600 "${filePath}" --out "${jpgPath}"`, { stdio: "pipe" });
          image_base64 = fs.readFileSync(jpgPath).toString("base64");
          image_media_type = "image/jpeg";
          fs.unlinkSync(jpgPath);
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
