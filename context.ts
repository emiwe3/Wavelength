import { getCanvasContext } from "./canvas.js";
import { getSlackContext } from "./slack.js";
// import { getGmailContext } from "./gmail.js";
// import { getCalendarContext } from "./calendar.js";

export async function getStudentContext(): Promise<string> {
  const [canvas, slack] = await Promise.all([
    getCanvasContext(),
    getSlackContext(),
    // getGmailContext(),
    // getCalendarContext(),
  ]);

  const sections: string[] = [];
  if (canvas) sections.push(`=== CANVAS ASSIGNMENTS ===\n${canvas}`);
  if (slack) sections.push(`=== SLACK ANNOUNCEMENTS ===\n${slack}`);

  return sections.join("\n\n");
}
