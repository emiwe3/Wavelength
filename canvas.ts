const CANVAS_BASE = process.env.CANVAS_BASE_URL;
const CANVAS_TOKEN = process.env.CANVAS_API_TOKEN;

export interface Assignment {
  name: string;
  due_at: string | null;
  course_name: string;
  points_possible: number;
  assignment_group_id?: number;
  submission_types?: string[];
  submission: { submitted_at: string | null } | null;
  // Calculated: this assignment's share of the final grade (0–100)
  grade_weight?: number;
}

export interface Announcement {
  title: string;
  message: string;
  posted_at: string;
  course_name: string;
  author_name?: string;
}

async function canvasFetch(
  path: string,
  token = CANVAS_TOKEN,
  base = CANVAS_BASE
): Promise<any> {
  const res = await fetch(`${base}/api/v1${path}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) throw new Error(`Canvas API error: ${res.status} ${path}`);
  return res.json();
}

function stripHtml(html: string): string {
  return html
    .replace(/<[^>]*>/g, " ")
    .replace(/&amp;/g, "&")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&nbsp;/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

export function isQuiz(a: Assignment): boolean {
  return (a.submission_types ?? []).includes("online_quiz");
}

// Returns urgency as % of final grade per day remaining.
// Falls back to raw points/days if group weights aren't set by the instructor.
export function urgencyScore(a: Assignment): number {
  const daysLeft = (new Date(a.due_at!).getTime() - Date.now()) / (1000 * 60 * 60 * 24);
  const weight = a.grade_weight ?? a.points_possible ?? 1;
  return weight / Math.max(daysLeft, 0.5);
}

export async function getUpcomingAssignments(
  token = CANVAS_TOKEN,
  base = CANVAS_BASE
): Promise<Assignment[]> {
  if (!base || !token) return [];

  const courses = await canvasFetch(
    "/courses?enrollment_state=active&per_page=50",
    token,
    base
  );

  const allAssignments: Assignment[] = [];
  const now = new Date();
  // 60-day window to catch exams and long-range planning
  const cutoff = new Date(now.getTime() + 60 * 24 * 60 * 60 * 1000);

  for (const course of courses) {
    try {
      const [assignments, groups] = await Promise.all([
        canvasFetch(
          `/courses/${course.id}/assignments?per_page=100&order_by=due_at&include[]=submission`,
          token,
          base
        ),
        canvasFetch(
          `/courses/${course.id}/assignment_groups?include[]=assignments`,
          token,
          base
        ).catch(() => []),
      ]);

      // Build map: group_id -> { group_weight, total_points_in_group }
      const groupMap = new Map<number, { weight: number; totalPoints: number }>();
      for (const g of groups) {
        if (!g.group_weight) continue;
        const totalPoints = (g.assignments ?? []).reduce(
          (sum: number, a: any) => sum + (a.points_possible ?? 0),
          0
        );
        groupMap.set(g.id, { weight: g.group_weight, totalPoints });
      }

      for (const a of assignments) {
        if (!a.due_at) continue;
        const due = new Date(a.due_at);
        if (due > now && due < cutoff) {
          // grade_weight = assignment's share of its group × group's % of final grade
          let grade_weight: number | undefined;
          const group = groupMap.get(a.assignment_group_id);
          if (group && group.totalPoints > 0) {
            grade_weight = (a.points_possible / group.totalPoints) * group.weight;
          }
          allAssignments.push({ ...a, course_name: course.name, grade_weight });
        }
      }
    } catch {
      // Skip inaccessible courses
    }
  }

  return allAssignments.sort(
    (a, b) => new Date(a.due_at!).getTime() - new Date(b.due_at!).getTime()
  );
}

export async function getCourseAnnouncements(
  token = CANVAS_TOKEN,
  base = CANVAS_BASE
): Promise<Announcement[]> {
  if (!base || !token) return [];

  const courses = await canvasFetch(
    "/courses?enrollment_state=active&per_page=50",
    token,
    base
  );

  const allAnnouncements: Announcement[] = [];

  for (const course of courses) {
    try {
      const topics = await canvasFetch(
        `/courses/${course.id}/discussion_topics?only_announcements=true&order_by=recent_activity&per_page=5`,
        token,
        base
      );
      for (const t of topics) {
        allAnnouncements.push({
          title: t.title,
          message: stripHtml(t.message ?? ""),
          posted_at: t.posted_at,
          course_name: course.name,
          author_name: t.author?.display_name,
        });
      }
    } catch {
      // Skip inaccessible courses
    }
  }

  // Most recent first, cap at 15
  return allAnnouncements
    .sort((a, b) => new Date(b.posted_at).getTime() - new Date(a.posted_at).getTime())
    .slice(0, 15);
}

export async function getCanvasContext(
  token = CANVAS_TOKEN,
  base = CANVAS_BASE
): Promise<string> {
  try {
    const [assignments, announcements] = await Promise.all([
      getUpcomingAssignments(token, base),
      getCourseAnnouncements(token, base),
    ]);

    const sections: string[] = [];

    if (assignments.length === 0) {
      sections.push("No upcoming assignments in the next 60 days.");
    } else {
      const lines = assignments.map((a) => {
        const due = new Date(a.due_at!);
        const daysLeft = Math.ceil((due.getTime() - Date.now()) / (1000 * 60 * 60 * 24));
        const submitted = a.submission?.submitted_at ? "✓ submitted" : "not submitted";
        const weight = a.grade_weight != null
          ? ` [${a.grade_weight.toFixed(1)}% of grade]`
          : a.points_possible ? ` [${a.points_possible}pts]` : "";
        const type = isQuiz(a) ? "Quiz" : "Assignment";
        const dueDateStr = due.toLocaleDateString("en-US", {
          weekday: "short",
          month: "short",
          day: "numeric",
        });
        // ~2% of grade per day remaining = high priority
        const urgent = urgencyScore(a) > 2 ? " ⚠️ HIGH PRIORITY" : "";
        return `- [${type}] ${a.course_name}: "${a.name}"${weight} due ${dueDateStr} (${daysLeft}d) — ${submitted}${urgent}`;
      });
      sections.push(`Upcoming assignments & quizzes:\n${lines.join("\n")}`);
    }

    if (announcements.length > 0) {
      const lines = announcements.map((ann) => {
        const date = new Date(ann.posted_at).toLocaleDateString("en-US", {
          month: "short",
          day: "numeric",
        });
        const author = ann.author_name ? ` (${ann.author_name})` : "";
        const preview = ann.message.slice(0, 250);
        return `- [${ann.course_name}]${author} "${ann.title}" on ${date}: ${preview}`;
      });
      sections.push(`Recent instructor announcements:\n${lines.join("\n")}`);
    }

    return sections.join("\n\n");
  } catch (err) {
    console.error("Canvas fetch failed:", err);
    return "";
  }
}
