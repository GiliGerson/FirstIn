import type { SupabaseClient } from "@supabase/supabase-js";
import type { ApplicationFields, Stage, UserState } from "./types";

/**
 * Job actions — the same effects as the Telegram buttons (worker/notify/bot.py), on the signed-in
 * user's own rows (RLS). Marking as applied opens an application (+ event) for the Pipeline;
 * undoing it removes the application while it is still at the "applied" stage.
 */
export async function setJobState(
  supabase: SupabaseClient,
  jobId: number,
  state: UserState,
  reason: string | null = null,
): Promise<void> {
  const { data: auth } = await supabase.auth.getUser();
  const userId = auth.user?.id;
  if (!userId) throw new Error("Not signed in");

  const { error } = await supabase
    .from("user_jobs")
    .update({ user_state: state, not_relevant_reason: state === "not_relevant" ? reason : null })
    .eq("user_id", userId)
    .eq("job_id", jobId);
  if (error) throw error;

  if (state === "applied") {
    const { data: existing, error: selectError } = await supabase
      .from("applications").select("id").eq("job_id", jobId).limit(1);
    if (selectError) throw selectError;
    if (!existing?.length) {
      const { data: app, error: insertError } = await supabase
        .from("applications").insert({ job_id: jobId, stage: "applied" }).select("id").single();
      if (insertError) throw insertError;
      await supabase.from("events").insert({ application_id: app.id, type: "applied", payload: { via: "dashboard" } });
    }
  } else {
    await supabase.from("applications").delete().eq("job_id", jobId).eq("stage", "applied");
  }
}

/** Move an application to another stage and record it in its history (`events`). */
export async function setApplicationStage(
  supabase: SupabaseClient,
  applicationId: number,
  from: Stage,
  to: Stage,
): Promise<void> {
  const { error } = await supabase.from("applications").update({ stage: to }).eq("id", applicationId);
  if (error) throw error;
  await supabase.from("events").insert({
    application_id: applicationId,
    type: "stage_change",
    payload: { from, to, via: "dashboard" },
  });
}

/** Edit free-form details of an application (notes, contact, follow-up date). */
export async function updateApplication(
  supabase: SupabaseClient,
  applicationId: number,
  fields: Partial<ApplicationFields>,
): Promise<void> {
  const { error } = await supabase.from("applications").update(fields).eq("id", applicationId);
  if (error) throw error;
}
