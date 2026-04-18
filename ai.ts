import Anthropic from "@anthropic-ai/sdk";
import { getStudentContext } from "./context.js";

const client = new Anthropic();

const SYSTEM_PROMPT = `You are PulsePoint, an AI academic assistant that lives in iMessage.
You have access to the student's Canvas assignments and help them stay on top of deadlines.
Be concise, friendly, and proactive. Format responses for iMessage (no markdown, keep it short).
If you have assignment data, lead with what's most urgent.`;

// Per-user conversation history
const histories = new Map<string, Anthropic.MessageParam[]>();

export async function getAIResponse(userMessage: string, userId: string): Promise<string> {
  const history = histories.get(userId) ?? [];
  const studentContext = await getStudentContext();

  const response = await client.messages.create({
    model: "claude-sonnet-4-6",
    max_tokens: 1024,
    system: [
      // Static instructions — cached for 5 minutes across repeated calls
      {
        type: "text",
        text: SYSTEM_PROMPT,
        cache_control: { type: "ephemeral" },
      },
      // Dynamic Canvas + Slack context — not cached (changes hourly)
      ...(studentContext ? [{ type: "text" as const, text: studentContext }] : []),
    ],
    messages: [
      ...history,
      { role: "user", content: userMessage },
    ],
  });

  const assistantText =
    response.content[0].type === "text" ? response.content[0].text : "";

  // Update history and keep last 20 turns
  const updated: Anthropic.MessageParam[] = [
    ...history,
    { role: "user", content: userMessage },
    { role: "assistant", content: assistantText },
  ];
  histories.set(userId, updated.slice(-20));

  return assistantText;
}
