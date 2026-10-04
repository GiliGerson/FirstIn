import { createServerClient } from "@supabase/ssr";
import { NextResponse, type NextRequest } from "next/server";

// Reachable without signing in. /reset-password is not: the email link signs the user in first.
const PUBLIC_PATHS = ["/", "/login", "/signup", "/forgot-password", "/auth/confirm"];
// Pages a signed-in user doesn't need — they go straight to the dashboard
const SIGNED_OUT_ONLY = ["/", "/login", "/signup", "/forgot-password"];

/**
 * Refreshes the Supabase session cookie on every request and sends signed-out visitors to /login.
 * This is an optimistic check only — data access is enforced by RLS in the database.
 */
export async function proxy(request: NextRequest) {
  let response = NextResponse.next({ request });

  const supabase = createServerClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY!,
    {
      cookies: {
        getAll() {
          return request.cookies.getAll();
        },
        setAll(cookiesToSet, headers) {
          cookiesToSet.forEach(({ name, value }) => request.cookies.set(name, value));
          response = NextResponse.next({ request });
          cookiesToSet.forEach(({ name, value, options }) => response.cookies.set(name, value, options));
          Object.entries(headers ?? {}).forEach(([key, value]) => response.headers.set(key, value));
        },
      },
    },
  );

  const { data } = await supabase.auth.getClaims();
  const signedIn = Boolean(data?.claims);
  const path = request.nextUrl.pathname;
  const isPublic = PUBLIC_PATHS.some((p) => path === p || (p !== "/" && path.startsWith(`${p}/`)));

  if (!signedIn && !isPublic) {
    return NextResponse.redirect(new URL("/login", request.url));
  }
  if (signedIn && SIGNED_OUT_ONLY.includes(path)) {
    return NextResponse.redirect(new URL("/dashboard", request.url));
  }
  return response;
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico|icon.svg|.*\\.(?:png|jpg|svg|ico)$).*)"],
};
