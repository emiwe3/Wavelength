import "dotenv/config";
import { im } from "./client.js";
import { getAIResponse } from "./ai.js";
import { postToSlack, postDeadlineReminder } from "./slack.js";

console.log("🤖 PulsePoint is starting...");

// Post a deadline digest to Slack on startup
await postDeadlineReminder();

for await (const event of im.messages.subscribe("message.received")) {
  const { message, chatGuid } = event;

  if (!message.text || message.isFromMe) continue;

  console.log(`📩 Received: "${message.text}" from ${chatGuid}`);

  const reply = await getAIResponse(message.text, String(chatGuid));
  await im.messages.send(chatGuid, reply);

  // Mirror the conversation to Slack
  await postToSlack(`💬 *iMessage from ${chatGuid}*\n> ${message.text}\n\n🤖 *PulsePoint:* ${reply}`);

  console.log(`📤 Replied: "${reply}"`);
}
