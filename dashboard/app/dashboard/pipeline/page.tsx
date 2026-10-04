import PipelineBoard from "@/components/PipelineBoard";
import { createClient } from "@/lib/supabase/server";
import { APPLICATION_SELECT, type Application } from "@/lib/types";

export const dynamic = "force-dynamic";

export default async function PipelinePage() {
  const supabase = await createClient();
  const { data, error } = await supabase
    .from("applications")
    .select(APPLICATION_SELECT)
    .order("applied_at", { ascending: false })
    .limit(1000);

  if (error) {
    return <p className="rounded-xl bg-bad-soft p-4 text-bad">Couldn&apos;t load applications: {error.message}</p>;
  }
  return <PipelineBoard initialApps={(data ?? []) as unknown as Application[]} />;
}
