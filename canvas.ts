const CANVAS_BASE = process.env.CANVAS_BASE_URL; // e.g. https://canvas.princeton.edu
const CANVAS_TOKEN = process.env.CANVAS_API_TOKEN;

interface Assignment {
  name: string;
  due_at: string | null;
  course_name: string;
  points_possible: number;
  submission: { submitted_at: string | null } | null;
}

async function canvasFetch(path: string) {
  const res = await fetch(`${CANVAS_BASE}/api/v1${path}`, {
    headers: { Authorization: `Bearer ${CANVAS_TOKEN}` },
  });
  if (!res.ok) throw new Error(`Canvas API error: ${res.status} ${path}`);
  return res.json();
}

export async function getUpcomingAssignments(): Promise<Assignment[]> {
  if (!CANVAS_BASE || !CANVAS_TOKEN) return [];

  // Get all enrolled courses
  const courses = await canvasFetch("/courses?enrollment_state=active&per_page=50");

  const allAssignments: Assignment[] = [];
  const now = new Date();
  const twoWeeksOut = new Date(now.getTime() + 14 * 24 * 60 * 60 * 1000);

  for (const course of courses) {
    try {
      const assignments = await canvasFetch(
        `/courses/${course.id}/assignments?per_page=50&order_by=due_at&include[]=submission`
      );
      for (const a of assignments) {
        if (!a.due_at) continue;
        const due = new Date(a.due_at);
        if (due > now && due < twoWeeksOut) {
          allAssignments.push({ ...a, course_name: course.name });
        }
      }
    } catch {
      // Skip courses we can't read
    }
  }

  // Sort by due date ascending
  return allAssignments.sort((a, b) =>
    new Date(a.due_at!).getTime() - new Date(b.due_at!).getTime()
  );
}

// Returns a plain-text summary for the AI system prompt
export async function getCanvasContext(): Promise<string> {
  try {
    const assignments = await getUpcomingAssignments();
    if (assignments.length === 0) return "No upcoming assignments in the next 2 weeks.";

    const lines = assignments.map((a) => {
      const due = new Date(a.due_at!);
      const daysLeft = Math.ceil((due.getTime() - Date.now()) / (1000 * 60 * 60 * 24));
      const submitted = a.submission?.submitted_at ? "✓ submitted" : "not submitted";
      return `- ${a.course_name}: "${a.name}" due in ${daysLeft}d (${submitted})`;
    });

    return `Upcoming assignments:\n${lines.join("\n")}`;
  } catch (err) {
    console.error("Canvas fetch failed:", err);
    return "";
  }
}
