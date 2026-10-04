import Link from "next/link";

/** Shared frame for the sign-in / sign-up / password pages. */
export default function AuthCard({ title, subtitle, children }: {
  title: string;
  subtitle?: string;
  children: React.ReactNode;
}) {
  return (
    <main className="flex min-h-screen items-center justify-center px-4">
      <div className="w-full max-w-sm rounded-2xl border border-border bg-surface p-7 shadow-sm">
        <Link href="/" className="mb-6 flex items-center gap-3">
          <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-accent text-lg font-bold text-white">F</span>
          <div>
            <h1 className="text-xl font-bold">{title}</h1>
            {subtitle && <p className="text-sm text-muted">{subtitle}</p>}
          </div>
        </Link>
        {children}
      </div>
    </main>
  );
}

export const inputClass =
  "mb-4 w-full rounded-lg border border-border bg-bg px-3 py-2 outline-none focus:border-accent";
export const buttonClass =
  "w-full rounded-lg bg-accent py-2.5 font-semibold text-white transition hover:opacity-90 disabled:opacity-60";
export const MIN_PASSWORD = 10;
