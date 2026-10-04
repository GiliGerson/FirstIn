import Link from "next/link";

const FEATURES = [
  {
    icon: "🔎",
    title: "Every source, one feed",
    text: "Company career sites (Greenhouse, Lever, Ashby, Comeet) and LinkedIn job alerts — collected, de-duplicated and kept fresh around the clock.",
  },
  {
    icon: "🎯",
    title: "Ranked for you",
    text: "Claude scores every student, internship and part-time role against your profile, with clear reasons and red flags like “requires 5 days a week”.",
  },
  {
    icon: "⚡",
    title: "Alerts in minutes",
    text: "Strong matches go straight to Telegram, so you can apply while the role is fresh. Everything else waits in a calm daily digest.",
  },
  {
    icon: "🗂",
    title: "Track every application",
    text: "One tap marks a job as applied. A simple board follows each application from applied to interview to offer.",
  },
];

const STEPS = [
  { title: "Sign up", text: "Create a free account in under a minute." },
  { title: "Tell us what you want", text: "Roles, cities, job types and how many days a week you can work." },
  { title: "Connect Telegram", text: "One tap — then matching jobs start arriving." },
];

export default function LandingPage() {
  return (
    <div className="min-h-screen">
      <header className="mx-auto flex max-w-6xl items-center gap-3 px-4 py-5">
        <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-accent text-sm font-bold text-white">F</span>
        <span className="text-lg font-bold">FirstIn</span>
        <nav className="ms-auto flex items-center gap-2">
          <Link href="/demo" className="rounded-lg px-3 py-1.5 text-sm font-medium text-muted hover:text-text">Demo</Link>
          <Link href="/login" className="rounded-lg px-3 py-1.5 text-sm font-medium text-muted hover:text-text">Sign in</Link>
          <Link href="/signup" className="rounded-lg bg-accent px-3 py-1.5 text-sm font-semibold text-white hover:opacity-90">
            Get started
          </Link>
        </nav>
      </header>

      <main>
        <section className="mx-auto grid max-w-6xl items-center gap-10 px-4 pb-16 pt-8 md:grid-cols-2 md:pt-16">
          <div>
            <p className="mb-4 inline-block rounded-full bg-accent-soft px-3 py-1 text-xs font-semibold text-accent">
              For students in Israel · Free
            </p>
            <h1 className="text-4xl font-extrabold leading-tight tracking-tight sm:text-5xl">
              Be first in line for student tech jobs.
            </h1>
            <p className="mt-5 max-w-lg text-lg leading-relaxed text-muted">
              Student roles close in days. FirstIn watches Israeli company career sites and LinkedIn for you,
              ranks every new role against your profile, and sends the best ones to Telegram — so you can apply first.
            </p>
            <div className="mt-8 flex flex-wrap gap-3">
              <Link href="/signup" className="rounded-xl bg-accent px-6 py-3 font-semibold text-white shadow-sm hover:opacity-90">
                Get started — it&apos;s free
              </Link>
              <Link href="/demo" className="rounded-xl border border-border bg-surface px-6 py-3 font-semibold hover:border-accent">
                See a live demo
              </Link>
            </div>
          </div>

          <div className="mx-auto w-full max-w-sm rounded-3xl border border-border bg-surface p-4 shadow-xl">
            <div className="mb-3 flex items-center gap-2 border-b border-border pb-3">
              <span className="flex h-8 w-8 items-center justify-center rounded-full bg-accent text-sm font-bold text-white">F</span>
              <div>
                <p className="text-sm font-semibold">FirstIn</p>
                <p className="text-xs text-muted">bot</p>
              </div>
            </div>
            <div className="rounded-2xl bg-surface-2 p-3 text-sm leading-relaxed">
              <p><span className="font-bold text-good">🟢 88</span> · <b>Software Engineering Student</b></p>
              <p className="text-muted">🏢 Example Tech · 📍 Tel Aviv (hybrid)</p>
              <p className="mt-2">✅ Student role in your top-priority field</p>
              <p>✅ Python and cloud — matches your skills</p>
              <p className="text-warn">⚠️ Days per week not stated</p>
            </div>
            <div className="mt-2 grid grid-cols-3 gap-1.5 text-center text-xs font-medium">
              <span className="rounded-lg bg-surface-2 py-2">✅ Applied</span>
              <span className="rounded-lg bg-surface-2 py-2">⭐ Save</span>
              <span className="rounded-lg bg-surface-2 py-2">👎 Not for me</span>
            </div>
          </div>
        </section>

        <section className="border-y border-border bg-surface">
          <div className="mx-auto grid max-w-6xl gap-6 px-4 py-14 sm:grid-cols-2 lg:grid-cols-4">
            {FEATURES.map((f) => (
              <div key={f.title}>
                <div className="mb-3 text-2xl">{f.icon}</div>
                <h3 className="font-semibold">{f.title}</h3>
                <p className="mt-1.5 text-sm leading-relaxed text-muted">{f.text}</p>
              </div>
            ))}
          </div>
        </section>

        <section className="mx-auto max-w-6xl px-4 py-16">
          <h2 className="text-center text-2xl font-bold sm:text-3xl">Three steps to your first match</h2>
          <ol className="mx-auto mt-10 grid max-w-4xl gap-6 sm:grid-cols-3">
            {STEPS.map((s, i) => (
              <li key={s.title} className="rounded-2xl border border-border bg-surface p-5">
                <span className="flex h-8 w-8 items-center justify-center rounded-full bg-accent-soft font-bold text-accent">{i + 1}</span>
                <h3 className="mt-3 font-semibold">{s.title}</h3>
                <p className="mt-1 text-sm text-muted">{s.text}</p>
              </li>
            ))}
          </ol>
          <div className="mt-10 text-center">
            <Link href="/signup" className="inline-block rounded-xl bg-accent px-6 py-3 font-semibold text-white hover:opacity-90">
              Create your account
            </Link>
            <p className="mt-3 text-xs text-muted">New accounts are reviewed before alerts start — usually within a day.</p>
          </div>
        </section>
      </main>

      <footer className="border-t border-border">
        <div className="mx-auto max-w-6xl px-4 py-8 text-sm text-muted">
          <p>
            FirstIn was built as a final project in the course <i>Autodidacticism in the 21st Century</i> at the
            Adelson School of Entrepreneurship, Reichman University.
          </p>
        </div>
      </footer>
    </div>
  );
}
