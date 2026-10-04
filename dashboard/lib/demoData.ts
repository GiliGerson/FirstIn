/** Sample data for the public /demo pages. Every company, job and application here is fictional. */
import type { Application, Job } from "./types";

const HOUR = 3600 * 1000;
const DAY = 24 * HOUR;

type Seed = {
  title: string; company: string; kind: "startup" | "enterprise"; location: string; hybrid?: boolean; remote?: boolean;
  type: "student" | "internship" | "part_time"; category: string; score: number; hoursAgo: number;
  sources: string[]; reasons: string[]; flags?: string[]; requirements: string[];
  state?: Job["user_state"];
};

const SEEDS: Seed[] = [
  { title: "Software Engineering Student", company: "Nimbus Labs", kind: "startup", location: "Tel Aviv", hybrid: true,
    type: "student", category: "Software Developer", score: 94, hoursAgo: 1, sources: ["greenhouse", "linkedin"],
    reasons: ["Student role in your top-priority field", "Backend in Python — matches your coursework", "2–3 days a week, fits your schedule"],
    requirements: ["Python", "SQL", "REST APIs"] },
  { title: "AI Engineer Intern", company: "Quanta AI", kind: "startup", location: "Herzliya", hybrid: true,
    type: "internship", category: "AI / ML Engineer", score: 89, hoursAgo: 3, sources: ["ashby"],
    reasons: ["Hands-on LLM work, your second-priority role", "Small team with direct mentoring"],
    flags: ["Internship length not stated"], requirements: ["Python", "LLMs", "Prompt engineering"] },
  { title: "Product Analyst — Student Position", company: "Mosaic Fintech", kind: "startup", location: "Tel Aviv",
    type: "student", category: "Product", score: 84, hoursAgo: 5, sources: ["comeet"],
    reasons: ["Student product role with SQL and dashboards", "Good fit for an entrepreneurship track"],
    requirements: ["SQL", "Excel", "Product sense"], state: "saved" },
  { title: "Full-Stack Developer (Student)", company: "Orbitly", kind: "startup", location: "Ramat Gan", remote: true,
    type: "student", category: "Software Developer", score: 81, hoursAgo: 8, sources: ["lever", "linkedin"],
    reasons: ["React + Node student role", "Remote-friendly"], flags: ["Asks for one production project"],
    requirements: ["React", "Node.js", "TypeScript"] },
  { title: "Data Science Student", company: "Lumen Health", kind: "enterprise", location: "Petah Tikva", hybrid: true,
    type: "student", category: "Data Analyst / Data Science", score: 77, hoursAgo: 20, sources: ["greenhouse"],
    reasons: ["Applied ML on real health data", "Clear student track"], requirements: ["Python", "Pandas", "Statistics"],
    state: "applied" },
  { title: "Cloud Automation Student", company: "Vertex Cloud", kind: "enterprise", location: "Herzliya",
    type: "student", category: "DevOps / Cloud", score: 71, hoursAgo: 26, sources: ["linkedin"],
    reasons: ["Automation with Python, close to software development"], flags: ["Requires 3 fixed office days"],
    requirements: ["Python", "Linux", "AWS"] },
  { title: "Security Research Intern", company: "Tessera Security", kind: "startup", location: "Tel Aviv",
    type: "internship", category: "Cybersecurity", score: 66, hoursAgo: 30, sources: ["comeet"],
    reasons: ["Strong team, but security isn't one of your target roles"], requirements: ["Networking", "Python"] },
  { title: "QA Automation Student", company: "Brightwave", kind: "enterprise", location: "Rehovot",
    type: "student", category: "QA / Test Automation", score: 58, hoursAgo: 44, sources: ["greenhouse"],
    reasons: ["Student role with coding, but QA is a lower priority"], flags: ["Commute to Rehovot"],
    requirements: ["Python", "Selenium"] },
  { title: "Robotics Software Student", company: "Kestrel Robotics", kind: "startup", location: "Haifa",
    type: "student", category: "Hardware / Embedded", score: 52, hoursAgo: 50, sources: ["lever"],
    reasons: ["Interesting product, but outside your preferred area"], flags: ["Located in Haifa"],
    requirements: ["C++", "ROS"] },
  { title: "Growth Marketing Student", company: "Cobalt Games", kind: "startup", location: "Tel Aviv",
    type: "part_time", category: "Marketing / Growth", score: 41, hoursAgo: 60, sources: ["linkedin"],
    reasons: ["Part-time, but not a tech role you're looking for"], requirements: ["Analytics", "Copywriting"],
    state: "not_relevant" },
];

export function demoJobs(now: number): Job[] {
  return SEEDS.map((s, i) => ({
    id: i + 1,
    title: s.title,
    url: "https://example.com/jobs/demo",
    canonical_url: null,
    location: s.location,
    is_hybrid: s.hybrid ?? false,
    is_remote: s.remote ?? false,
    job_type: s.type,
    posted_at: null,
    first_seen_at: new Date(now - s.hoursAgo * HOUR).toISOString(),
    status: "open",
    companies: { name: s.company, kind: s.kind },
    job_sources: s.sources.map((source) => ({ source })),
    match_score: s.score,
    match_reasons: s.reasons,
    red_flags: s.flags ?? [],
    requirements: s.requirements,
    role_category: s.category,
    user_state: s.state ?? "new",
    not_relevant_reason: s.state === "not_relevant" ? "Role" : null,
  }));
}

type AppSeed = { title: string; company: string; daysAgo: number; stage: Application["stage"]; path: string[];
                 notes?: string; email?: string };

const APPS: AppSeed[] = [
  { title: "Data Science Student", company: "Lumen Health", daysAgo: 1, stage: "applied", path: [] },
  { title: "Backend Developer — Student", company: "Parallax Data", daysAgo: 6, stage: "screening", path: ["screening"],
    email: "Thanks for applying — a recruiter will call you this week" },
  { title: "Junior Product Analyst (Student)", company: "Atlas Mobility", daysAgo: 12, stage: "interview",
    path: ["screening", "interview"], notes: "Interview Tuesday 14:00 with the product lead",
    email: "Invitation: interview with the product team" },
  { title: "ML Engineering Intern", company: "Quanta AI", daysAgo: 15, stage: "home_assignment",
    path: ["screening", "home_assignment"], email: "Next step: a short home assignment" },
  { title: "Student Developer", company: "Mosaic Fintech", daysAgo: 25, stage: "offer",
    path: ["screening", "interview", "offer"], email: "We're happy to offer you the position 🎉" },
  { title: "Software Student", company: "Brightwave", daysAgo: 20, stage: "rejected", path: ["screening", "rejected"] },
];

export function demoApplications(now: number): Application[] {
  return APPS.map((a, i) => {
    const applied = now - a.daysAgo * DAY;
    let from = "applied";
    const events = [
      { id: i * 10, type: "applied", occurred_at: new Date(applied).toISOString(), payload: { via: "telegram" } },
      ...a.path.map((to, k) => {
        const e = { id: i * 10 + k + 1, type: "stage_change",
                    occurred_at: new Date(applied + (k + 1) * 2 * DAY).toISOString(),
                    payload: { from, to, via: "email" } };
        from = to;
        return e;
      }),
    ];
    return {
      id: i + 1, job_id: null, applied_at: new Date(applied).toISOString(), stage: a.stage, cv_version_path: null,
      notes: a.notes ?? null, contact_name: null, contact_email: null,
      next_followup_at: a.stage === "applied" ? new Date(now - HOUR).toISOString() : null,
      jobs: { title: a.title, url: "https://example.com/jobs/demo", canonical_url: null, location: "Tel Aviv",
              companies: { name: a.company }, user_jobs: [{ role_category: i % 2 ? "Software Developer" : "Product" }] },
      events,
      emails: a.email ? [{ id: i, subject: a.email, summary: null, received_at: new Date(applied + DAY).toISOString() }] : [],
    };
  });
}
