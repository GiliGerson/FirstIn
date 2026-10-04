import { createBrowserClient } from "@supabase/ssr";

/** Supabase client for Client Components. Access is limited by RLS to the dashboard owner. */
export function createClient() {
  return createBrowserClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY!,
  );
}
