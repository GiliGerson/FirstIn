export type UserState = "new" | "saved" | "not_relevant" | "applied";
export type JobType = "student" | "part_time" | "internship" | "other";

/** One job as the signed-in user sees it: the shared job + their own score and state (user_jobs). */
export type Job = {
  id: number;
  title: string;
  url: string | null;
  canonical_url: string | null;
  location: string | null;
  is_hybrid: boolean | null;
  is_remote: boolean | null;
  job_type: JobType | null;
  posted_at: string | null;
  first_seen_at: string;
  status: "open" | "closed";
  companies: { name: string; kind: "startup" | "enterprise" | null } | null;
  job_sources: { source: string }[];
  // per-user
  match_score: number | null;
  match_reasons: string[];
  red_flags: string[];
  requirements: string[];
  role_category: string | null;
  user_state: UserState;
  not_relevant_reason: string | null;
};

export type UserJobRow = Omit<Job, keyof SharedJob | "id"> & { job_id: number; jobs: SharedJob };
type SharedJob = Pick<Job,
  "title" | "url" | "canonical_url" | "location" | "is_hybrid" | "is_remote" | "job_type" | "posted_at" |
  "first_seen_at" | "status" | "companies" | "job_sources">;

export const USER_JOB_SELECT =
  "job_id,match_score,match_reasons,red_flags,requirements,role_category,user_state,not_relevant_reason," +
  "jobs!inner(title,url,canonical_url,location,is_hybrid,is_remote,job_type,posted_at,first_seen_at,status," +
  "companies(name,kind),job_sources(source))";

export function toJob(row: UserJobRow): Job {
  const { jobs, job_id, ...mine } = row;
  return { ...jobs, ...mine, id: job_id };
}

export type Stage =
  | "applied" | "screening" | "interview" | "home_assignment" | "offer" | "rejected" | "ghosted" | "withdrawn";

export type ApplicationFields = {
  notes: string | null;
  contact_name: string | null;
  contact_email: string | null;
  next_followup_at: string | null;
};

export type AppEvent = { id: number; type: string; occurred_at: string; payload: Record<string, unknown> };

export type Application = ApplicationFields & {
  id: number;
  job_id: number | null;
  applied_at: string;
  stage: Stage;
  cv_version_path: string | null;
  jobs: {
    title: string;
    url: string | null;
    canonical_url: string | null;
    location: string | null;
    companies: { name: string } | null;
    user_jobs: { role_category: string | null }[];   // the signed-in user's own row (RLS)
  } | null;
  events: AppEvent[];
  emails: { id: number; subject: string | null; summary: string | null; received_at: string | null }[];
};

export const APPLICATION_SELECT =
  "id,job_id,applied_at,stage,cv_version_path,notes,contact_name,contact_email,next_followup_at," +
  "jobs(title,url,canonical_url,location,companies(name),user_jobs(role_category))," +
  "events(id,type,occurred_at,payload),emails(id,subject,summary,received_at)";

export type Profile = {
  user_id: string;
  display_name: string | null;
  field_of_study: string | null;
  study_year: number | null;
  languages: string[];
  status: "pending" | "approved" | "blocked";
  is_owner: boolean;
  onboarding_done: boolean;
  telegram_chat_id: number | null;
};
