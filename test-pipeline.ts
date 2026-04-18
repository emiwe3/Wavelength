import "dotenv/config";
import { getStudentContext } from "./context.js";
import { getAIResponse } from "./ai.js";

const SIMULATED_MESSAGES = [
  "hey what do I have due this week?",
  "which assignment should I actually prioritize right now?",
  "do I have any quizzes or exams coming up?",
  "are there any announcements from my professors I should know about?",
  "I only have 2 hours tonight, what should I work on?",
];

const TEST_USER = "test-student-001";

console.log("🔍 Fetching Canvas context...\n");
const context = await getStudentContext();

if (!context) {
  console.log("⚠️  No Canvas context returned — check CANVAS_BASE_URL and CANVAS_API_TOKEN in .env");
  process.exit(1);
}

console.log("=== CANVAS CONTEXT LOADED ===");
console.log(context);
console.log("\n" + "=".repeat(50) + "\n");

console.log("🤖 Running simulated student conversation...\n");

for (const message of SIMULATED_MESSAGES) {
  console.log(`👤 Student: ${message}`);
  const reply = await getAIResponse(message, TEST_USER);
  console.log(`🤖 PulsePoint: ${reply}`);
  console.log();
}

console.log("✅ Pipeline test complete.");
