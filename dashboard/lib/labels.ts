export const SOURCE_NAMES: Record<string, string> = {
  linkedin: "LinkedIn",
  gmail: "Email",
  greenhouse: "Greenhouse",
  lever: "Lever",
  ashby: "Ashby",
  comeet: "Comeet",
  workday: "Workday",
  smartrecruiters: "SmartRecruiters",
};

export const JOB_TYPE_LABEL: Record<string, string> = {
  student: "Student",
  internship: "Internship",
  part_time: "Part-time",
  other: "Other",
};

export const STATE_LABEL: Record<string, string> = {
  new: "New",
  saved: "Saved",
  applied: "Applied",
  not_relevant: "Not relevant",
};

/** Pipeline columns, in order. Closed outcomes share one column. */
export const STAGES = ["applied", "screening", "interview", "home_assignment", "offer"] as const;
export const CLOSED_STAGES = ["rejected", "ghosted", "withdrawn"] as const;

export const STAGE_LABEL: Record<string, string> = {
  applied: "Applied",
  screening: "Screening",
  interview: "Interview",
  home_assignment: "Home assignment",
  offer: "Offer 🎉",
  rejected: "Rejected",
  ghosted: "No reply",
  withdrawn: "Withdrawn",
};

/** FR8 feedback reasons (the Telegram bot uses the same set) */
export const NOT_RELEVANT_REASONS = ["Location", "Hours", "Role", "Company", "Other"];

export function scoreTone(score: number | null): "good" | "warn" | "bad" | "none" {
  if (score === null) return "none";
  if (score >= 75) return "good";
  if (score >= 50) return "warn";
  return "bad";
}

const rtf = new Intl.RelativeTimeFormat("en", { numeric: "auto" });

export function timeAgo(iso: string | null, now: number = Date.now()): string {
  if (!iso) return "";
  const minutes = Math.round((new Date(iso).getTime() - now) / 60000);
  if (Math.abs(minutes) < 60) return rtf.format(minutes, "minute");
  const hours = Math.round(minutes / 60);
  if (Math.abs(hours) < 24) return rtf.format(hours, "hour");
  return rtf.format(Math.round(hours / 24), "day");
}

export function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });
}
