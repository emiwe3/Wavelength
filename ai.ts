import Anthropic from "@anthropic-ai/sdk";
import { getStudentContext } from "./context.js";

const client = new Anthropic({ apiKey: process.env.ANTHROPIC_API_KEY });

const SYSTEM_PROMPT = `You are PulsePoint, an AI academic assistant that lives in iMessage.
You have access to the student's Canvas assignments, Google Calendar, Gmail, and Slack.
Be concise, friendly, and proactive. Format responses for iMessage (no markdown, keep it short).
If you have assignment data, lead with what's most urgent.`;

// Per-user conversation history for multi-turn chat
const histories = new Map<string, Anthropic.MessageParam[]>();

export async function getAIResponse(userMessage: string, userId: string): Promise<string> {
  const history = histories.get(userId) ?? [];

  const studentContext = await getStudentContext();
  const systemWithContext = studentContext
    ? `${SYSTEM_PROMPT}\n\n${studentContext}`
    : SYSTEM_PROMPT;

  const messages: Anthropic.MessageParam[] = [
    ...history,
    { role: "user", content: userMessage },
  ];

  const response = await client.messages.create({
    model: "claude-opus-4-7",
    max_tokens: 1024,
    system: systemWithContext,
    messages,
  });

  const assistantText = response.content[0].type === "text" ? response.content[0].text : "";

  history.push({ role: "user", content: userMessage });
  history.push({ role: "assistant", content: assistantText });

  // Keep last 20 turns per user
  histories.set(userId, history.slice(-20));

  return assistantText;
}
