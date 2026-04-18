/**
 * bridge.mjs — iMessage <-> Python backend bridge via @photon-ai/imessage-kit
 * Requires Full Disk Access for your terminal in System Settings → Privacy & Security
 * Run with: node bridge.mjs
 */

import { IMessageSDK } from "@photon-ai/imessage-kit";

const BACKEND_URL = process.env.BACKEND_URL || "http://localhost:8000";

const sdk = new IMessageSDK();

console.log("🌉 iMessage bridge starting...");

await sdk.startWatching({
  onDirectMessage: async (msg) => {
    if (msg.isFromMe || !msg.text) return;

    console.log(`📩 From ${msg.sender}: ${msg.text}`);

    try {
      const res = await fetch(`${BACKEND_URL}/api/bot/message`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          phone: msg.sender,
          chat_guid: msg.chatId,
          text: msg.text,
        }),
      });

      const data = await res.json();
      if (data.reply) {
        await sdk.send(msg.sender, data.reply);
        console.log(`📤 Replied: ${data.reply}`);
      }
    } catch (err) {
      console.error("❌ Backend error:", err.message);
    }
  },
});

console.log("✅ Listening for iMessages...");
