import { redirect } from "next/navigation";
import OnboardingWizard from "@/components/OnboardingWizard";
import { createClient } from "@/lib/supabase/server";
import type { Profile } from "@/lib/types";

export const dynamic = "force-dynamic";

export default async function OnboardingPage() {
  const supabase = await createClient();
  const { data: claims } = await supabase.auth.getClaims();
  if (!claims?.claims) redirect("/login");

  const { data: profile } = await supabase.from("profiles").select("*").maybeSingle();
  if (!profile) redirect("/login");
  if (profile.onboarding_done) redirect("/dashboard");
  return <OnboardingWizard profile={profile as Profile} botUsername={process.env.NEXT_PUBLIC_TELEGRAM_BOT_USERNAME} />;
}
