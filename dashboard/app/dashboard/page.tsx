import JobFeed from "@/components/JobFeed";
import { createClient } from "@/lib/supabase/server";
import { USER_JOB_SELECT, toJob, type UserJobRow } from "@/lib/types";

export const dynamic = "force-dynamic";

export default async function FeedPage() {
  const supabase = await createClient();
  const { data, error } = await supabase
    .from("user_jobs")
    .select(USER_JOB_SELECT)
    .order("match_score", { ascending: false, nullsFirst: false })
    .limit(2000);

  if (error) {
    return <p className="rounded-xl bg-bad-soft p-4 text-bad">Couldn&apos;t load jobs: {error.message}</p>;
  }
  return <JobFeed initialJobs={((data ?? []) as unknown as UserJobRow[]).map(toJob)} />;
}
