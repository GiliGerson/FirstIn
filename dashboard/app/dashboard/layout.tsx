import { redirect } from "next/navigation";
import Nav from "@/components/Nav";
import TelegramConnect from "@/components/TelegramConnect";
import { createClient } from "@/lib/supabase/server";
import type { Profile } from "@/lib/types";

export default async function DashboardLayout({ children }: LayoutProps<"/dashboard">) {
  const supabase = await createClient();
  const { data } = await supabase.auth.getClaims();
  if (!data?.claims) redirect("/login");

  const { data: row } = await supabase.from("profiles").select("*").maybeSingle();
  const profile = row as Profile | null;
  if (!profile || !profile.onboarding_done) redirect("/onboarding");

  return (
    <div className="min-h-screen">
      <header className="sticky top-0 z-20 border-b border-border bg-surface/90 backdrop-blur">
        <div className="mx-auto flex max-w-6xl items-center gap-3 px-4 py-3">
          <span className="flex shrink-0 items-center gap-2 font-bold">
            <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-accent text-sm text-white">F</span>
            <span className="hidden sm:inline">FirstIn</span>
          </span>
          {profile.status === "approved" && <Nav />}
          <form action="/auth/signout" method="post" className="ms-auto shrink-0">
            <button className="rounded-lg px-2 py-1 text-sm text-muted hover:text-text">Sign out</button>
          </form>
        </div>
      </header>
      <main className="mx-auto max-w-6xl px-4 py-6">
        {profile.status === "approved" ? children : profile.status === "blocked" ? (
          <Notice title="Access unavailable">
            Your account doesn&apos;t have access to FirstIn right now.
          </Notice>
        ) : (
          <Notice title={`Thanks${profile.display_name ? `, ${profile.display_name}` : ""}! You're on the list 🎉`}>
            <p>
              New accounts are reviewed before alerts start — usually within a day. As soon as yours is approved,
              matching jobs will appear here and on Telegram.
            </p>
            <div className="mx-auto mt-6 max-w-xs">
              <TelegramConnect connected={Boolean(profile.telegram_chat_id)}
                botUsername={process.env.NEXT_PUBLIC_TELEGRAM_BOT_USERNAME} />
            </div>
          </Notice>
        )}
      </main>
    </div>
  );
}

function Notice({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="mx-auto max-w-lg rounded-2xl border border-border bg-surface p-8 text-center">
      <p className="text-lg font-semibold">{title}</p>
      <div className="mt-3 text-sm leading-relaxed text-muted">{children}</div>
    </div>
  );
}
