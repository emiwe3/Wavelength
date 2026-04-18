import { getCanvasContext } from "./canvas.js";
import { getSlackContext } from "./slack.js";
import { getAIResponse } from "./ai.js";

console.log("=== SOURCE CHECK ===\n");

const [canvas, slack] = await Promise.all([
  getCanvasContext().catch((e) => `ERROR: ${e.message}`),
  getSlackContext().catch((e) => `ERROR: ${e.message}`),
]);

console.log("📚 CANVAS");
const canvasLines = canvas?.split("\n").slice(0, 5) ?? [];
canvasLines.forEach((l) => console.log(" ", l));
console.log(canvas ? "  ✅ Connected" : "  ❌ No data");

console.log("\n💬 SLACK");
const slackLines = slack?.split("\n").slice(0, 5) ?? [];
slackLines.forEach((l) => console.log(" ", l));
console.log(slack && slack !== "No recent Slack announcements." ? "  ✅ Connected" : "  ⚠️  No messages or not connected");

console.log("\n📧 GMAIL");
console.log("  ⏳ Not yet wired up in TypeScript (implemented in backend/gmail.py)");

console.log("\n📅 GOOGLE CALENDAR");
console.log("  ⏳ Not yet wired up in TypeScript (implemented in backend/calendar_sync.py)");

console.log("\n=== SIMULATING STUDENT MESSAGE ===");
const question = "what's going on recently";
console.log(`Student: "${question}"\n`);
const response = await getAIResponse(question, "test-student");
console.log(`PulsePoint: ${response}`);
