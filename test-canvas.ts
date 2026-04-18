import "dotenv/config";
import { getUpcomingAssignments, getCourseAnnouncements, isQuiz, urgencyScore } from "./canvas.js";

const base = process.env.CANVAS_BASE_URL;
const token = process.env.CANVAS_API_TOKEN;

if (!base || !token) {
  console.error("❌ Missing CANVAS_BASE_URL or CANVAS_API_TOKEN in .env");
  process.exit(1);
}

console.log(`\n🔗 Connecting to Canvas at ${base}...\n`);

// ── Assignments & Quizzes ────────────────────────────────────────────────────
console.log("📚 Fetching upcoming assignments & quizzes (60-day window)...\n");
const assignments = await getUpcomingAssignments();

if (assignments.length === 0) {
  console.log("  No upcoming assignments found.\n");
} else {
  for (const a of assignments) {
    const due = new Date(a.due_at!);
    const daysLeft = Math.ceil((due.getTime() - Date.now()) / (1000 * 60 * 60 * 24));
    const submitted = a.submission?.submitted_at ? "✅ submitted" : "⏳ not submitted";
    const type = isQuiz(a) ? "Quiz" : "Assignment";
    const pts = a.points_possible ? `${a.points_possible}pts` : "no points";
    const urgency = urgencyScore(a).toFixed(1);
    const dueDateStr = due.toLocaleDateString("en-US", {
      weekday: "short", month: "short", day: "numeric",
    });
    console.log(`  [${type}] ${a.course_name}`);
    console.log(`    "${a.name}"`);
    console.log(`    Due: ${dueDateStr} (${daysLeft} days) | ${pts} | Urgency: ${urgency} | ${submitted}`);
    console.log();
  }
  console.log(`  Total: ${assignments.length} item(s)\n`);
}

// ── Announcements ────────────────────────────────────────────────────────────
console.log("📢 Fetching instructor announcements...\n");
const announcements = await getCourseAnnouncements();

if (announcements.length === 0) {
  console.log("  No recent announcements found.\n");
} else {
  for (const ann of announcements) {
    const date = new Date(ann.posted_at).toLocaleDateString("en-US", {
      month: "short", day: "numeric",
    });
    const author = ann.author_name ? ` by ${ann.author_name}` : "";
    const preview = ann.message.slice(0, 300);
    console.log(`  [${ann.course_name}] "${ann.title}" — ${date}${author}`);
    console.log(`    ${preview}${ann.message.length > 300 ? "..." : ""}`);
    console.log();
  }
  console.log(`  Total: ${announcements.length} announcement(s)\n`);
}

console.log("✅ Canvas test complete.");
