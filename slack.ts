import { WebClient } from "@slack/web-api";
import { getUpcomingAssignments } from "./canvas.js";

const slack = new WebClient(process.env.SLACK_BOT_TOKEN);
const CHANNEL = process.env.SLACK_CHANNEL_ID!;

export async function postToSlack(text: string): Promise<void> {
  await slack.chat.postMessage({ channel: CHANNEL, text });
}

export async function getSlackContext(): Promise<string> {
  try {
    const result = await slack.conversations.history({ channel: CHANNEL, limit: 20 });
    const messages = result.messages ?? [];
    if (messages.length === 0) return "No recent Slack announcements.";

    const lines = messages
      .filter((m) => m.text && m.text.trim().length > 0)
      .map((m) => `- ${m.text}`);

    return `Recent announcements:\n${lines.join("\n")}`;
  } catch (err) {
    console.error("Slack fetch failed:", err);
    return "";
  }
}

export async function postDeadlineReminder(): Promise<void> {
  const assignments = await getUpcomingAssignments();
  if (assignments.length === 0) {
    await postToSlack("No upcoming assignments in the next 2 weeks. You're all caught up!");
    return;
  }

  const lines = assignments.map((a) => {
    const due = new Date(a.due_at!);
    const daysLeft = Math.ceil((due.getTime() - Date.now()) / (1000 * 60 * 60 * 24));
    const submitted = a.submission?.submitted_at ? "✅ submitted" : "⏳ not submitted";
    const dueDateStr = due.toLocaleDateString("en-US", { weekday: "short", month: "short", day: "numeric" });
    return `• *${a.course_name}*: ${a.name} — due ${dueDateStr} (${daysLeft}d) ${submitted}`;
  });

  const urgent = assignments.filter((a) => {
    const daysLeft = Math.ceil((new Date(a.due_at!).getTime() - Date.now()) / (1000 * 60 * 60 * 24));
    return daysLeft <= 2;
  });

  const header = urgent.length > 0
    ? `🚨 *PulsePoint Deadline Alert* — ${urgent.length} assignment(s) due within 2 days!`
    : `📚 *PulsePoint Deadline Digest* — ${assignments.length} upcoming assignment(s)`;

  await postToSlack(`${header}\n\n${lines.join("\n")}`);
}
