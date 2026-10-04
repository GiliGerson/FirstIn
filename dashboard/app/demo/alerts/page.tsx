/** What the Telegram bot sends — rendered as chat bubbles (sample data). */

function Bubble({ children, buttons }: { children: React.ReactNode; buttons?: string[][] }) {
  return (
    <div className="max-w-md">
      <div className="rounded-2xl rounded-tl-sm bg-surface-2 p-3.5 text-sm leading-relaxed shadow-sm">{children}</div>
      {buttons && (
        <div className="mt-1.5 space-y-1.5">
          {buttons.map((row, i) => (
            <div key={i} className="grid gap-1.5" style={{ gridTemplateColumns: `repeat(${row.length}, minmax(0, 1fr))` }}>
              {row.map((b) => (
                <span key={b} className="rounded-lg bg-surface-2 py-2 text-center text-xs font-medium">{b}</span>
              ))}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default function DemoAlertsPage() {
  return (
    <div className="mx-auto max-w-xl rounded-3xl border border-border bg-surface p-4 shadow-sm sm:p-6">
      <div className="mb-5 flex items-center gap-3 border-b border-border pb-4">
        <span className="flex h-10 w-10 items-center justify-center rounded-full bg-accent font-bold text-white">F</span>
        <div>
          <p className="font-semibold">FirstIn</p>
          <p className="text-xs text-muted">bot</p>
        </div>
      </div>

      <div className="space-y-5">
        <Bubble buttons={[["🔗 Open job"], ["✅ Applied", "⭐ Save", "👎 Not for me"]]}>
          <p>🟢 <b>94</b> · <b>Software Engineering Student</b></p>
          <p className="text-muted">🏢 Nimbus Labs · 📍 Tel Aviv (hybrid)</p>
          <p>🏷 Student position · Software Developer</p>
          <p className="mt-2">✅ Student role in your top-priority field</p>
          <p>✅ Backend in Python — matches your coursework</p>
          <p>✅ 2–3 days a week, fits your schedule</p>
          <p className="mt-2 text-muted">🔎 Source: Greenhouse + LinkedIn</p>
        </Bubble>

        <Bubble>
          <p>📬 <b>Application update: interview invitation</b></p>
          <p className="text-muted">From: Atlas Mobility Recruiting</p>
          <p className="mt-2">They&apos;d like to schedule an interview with the product team next week.</p>
          <p className="mt-2">🗂 Your application card moved to: Interview</p>
        </Bubble>

        <Bubble>
          <p>🌙 <b>Daily digest</b> · 6 jobs scored 50–74</p>
          <p className="mt-2">🟡 <b>71</b> · Cloud Automation Student — Vertex Cloud · Herzliya</p>
          <p>🟠 <b>66</b> · Security Research Intern — Tessera Security · Tel Aviv</p>
          <p>🟠 <b>58</b> · QA Automation Student — Brightwave · Rehovot</p>
          <p className="text-muted">…and 3 more on your dashboard</p>
        </Bubble>
      </div>
    </div>
  );
}
