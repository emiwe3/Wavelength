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
        const { execSync } = await import("child_process");
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

    const text = row.text?.trim();
    if (!text) continue;

    // Check if message contains a maps URL or raw coordinates
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
