/** Only same-site paths: "/\\evil.com" and "//evil.com" resolve to other hosts and are rejected. */
export function safeRedirectPath(next: string | null, origin: string): string {
  if (!next) return "/dashboard";
  try {
    const url = new URL(next, origin);
    return url.origin === origin ? `${url.pathname}${url.search}` : "/dashboard";
  } catch {
    return "/dashboard";
  }
}
