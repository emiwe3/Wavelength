import Anthropic from "@anthropic-ai/sdk";
import { getStudentContext } from "./context.js";

const genai = new GoogleGenAI({ apiKey: process.env.GEMINI_API_KEY });

const SYSTEM_PROMPT = `You are PulsePoint, an AI academic assistant that lives in iMessage.
You have access to the student's Canvas assignments, Google Calendar, Gmail, and Slack.
Be concise, friendly, and proactive. Format responses for iMessage (no markdown, keep it short).
If you have assignment data, lead with what's most urgent.`;

// Per-user conversation history for multi-turn chat
const histories = new Map<string, { role: string; parts: { text: string }[] }[]>();

export async function getAIResponse(userMessage: string, userId: string): Promise<string> {
  const history = histories.get(userId) ?? [];
  const studentContext = await getStudentContext();
  const systemWithContext = studentContext
    ? `${SYSTEM_PROMPT}\n\n${studentContext}`
    : SYSTEM_PROMPT;

  const chat = genai.chats.create({
    model: "gemini-2.0-flash",
    config: { systemInstruction: systemWithContext },
    history,
  });

  const response = await chat.sendMessage({ message: userMessage });
  const assistantText = response.text ?? "";

  // Update history with new turns
  history.push({ role: "user", parts: [{ text: userMessage }] });
  history.push({ role: "model", parts: [{ text: assistantText }] });

  // Keep last 20 turns per user
  histories.set(userId, history.slice(-20));

  return assistantText;
}
