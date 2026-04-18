import { WebClient } from "@slack/web-api";
import { getUpcomingAssignments } from "./canvas.js";

const slack = new WebClient(process.env.SLACK_BOT_TOKEN);
const CHANNEL = process.env.SLACK_CHANNEL_ID!;

export async function postToSlack(text: string): Promise<void> {
  await slack.chat.postMessage({ channel: CHANNEL, text });
}

export async function joinAllChannels(): Promise<void> {
  try {
    const listResult = await slack.conversations.list({ types: "public_channel", limit: 200 });
    const channels = listResult.channels ?? [];
    for (const channel of channels) {
      if (!channel.id || channel.is_member) continue;
      try {
        await slack.conversations.join({ channel: channel.id });
      } catch {
        // skip channels that can't be joined
      }
    }
  } catch (err) {
    console.error("Failed to join channels:", err);
  }
}

export async function getSlackContext(): Promise<string> {
  await joinAllChannels();
  try {
    const listResult = await slack.conversations.list({ types: "public_channel", limit: 200 });
    const channels = listResult.channels ?? [];

    const sections: string[] = [];

    for (const channel of channels) {
      if (!channel.id || !channel.name) continue;
      try {
        const result = await slack.conversations.history({ channel: channel.id, limit: 10 });
        const messages = (result.messages ?? []).filter((m) => m.text && m.text.trim().length > 0);
        if (messages.length === 0) continue;
        const lines = messages.map((m) => `  - ${m.text}`);
        sections.push(`#${channel.name}:\n${lines.join("\n")}`);
      } catch {
        // bot not in channel, skip
      }
    }

    if (sections.length === 0) return "No recent Slack announcements.";
    return `Recent Slack messages:\n\n${sections.join("\n\n")}`;
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

// test
const ctx = await getSlackContext();
console.log(ctx);
