import { getSlackContext } from "./slack.js";
import { getAIResponse } from "./ai.js";

console.log("Fetching Slack messages...\n");
const ctx = await getSlackContext();
console.log("=== SLACK CONTEXT ===");
console.log(ctx);

const scenarios = [
  "What's going on in my Slack workspace today?",
  "Are there any important announcements I should know about?",
  "I'm feeling overwhelmed, what should I focus on?",
];

console.log("\n=== CLAUDE RESPONSES ===");
for (const q of scenarios) {
  console.log(`\nQ: ${q}`);
  const answer = await getAIResponse(q, "test-user");
  console.log(`A: ${answer}`);
}
