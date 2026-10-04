import type { Application } from "./types";

const DAY = 24 * 3600 * 1000;
const RESPONDED = new Set(["screening", "interview", "home_assignment", "offer", "rejected"]);

export type PipelineStats = {
  thisWeek: number;
  total: number;
  responseRate: number | null;     // % of applications that got any answer (excluding withdrawn)
  avgDaysToResponse: number | null;
  byCategory: [string, number][];
  followupsDue: number;
};

/** First moment the company answered: the earliest stage change away from "applied". */
function firstResponseAt(app: Application): number | null {
  const times = app.events
    .filter((e) => e.type === "stage_change" && e.payload?.from === "applied")
    .map((e) => new Date(e.occurred_at).getTime());
  return times.length ? Math.min(...times) : null;
}

export function pipelineStats(apps: Application[], now: number): PipelineStats {
  const counted = apps.filter((a) => a.stage !== "withdrawn");
  const responded = counted.filter((a) => RESPONDED.has(a.stage));
  const delays = responded
    .map((a) => {
      const t = firstResponseAt(a);
      return t === null ? null : (t - new Date(a.applied_at).getTime()) / DAY;
    })
    .filter((d): d is number => d !== null && d >= 0);

  const categories = new Map<string, number>();
  for (const a of apps) {
    const c = a.jobs?.user_jobs?.[0]?.role_category || "Other";
    categories.set(c, (categories.get(c) ?? 0) + 1);
  }

  return {
    thisWeek: apps.filter((a) => now - new Date(a.applied_at).getTime() <= 7 * DAY).length,
    total: apps.length,
    responseRate: counted.length ? Math.round((responded.length / counted.length) * 100) : null,
    avgDaysToResponse: delays.length ? Math.round((delays.reduce((s, d) => s + d, 0) / delays.length) * 10) / 10 : null,
    byCategory: [...categories.entries()].sort((a, b) => b[1] - a[1]),
    followupsDue: apps.filter(
      (a) => a.next_followup_at && new Date(a.next_followup_at).getTime() <= now
        && !["offer", "rejected", "ghosted", "withdrawn"].includes(a.stage),
    ).length,
  };
}
