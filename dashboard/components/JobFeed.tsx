"use client";

import { useMemo, useState } from "react";
import { setJobState } from "@/lib/actions";
import { JOB_TYPE_LABEL, NOT_RELEVANT_REASONS, SOURCE_NAMES, STATE_LABEL, scoreTone, timeAgo } from "@/lib/labels";
import { safeUrl } from "@/lib/safeUrl";
import { createClient } from "@/lib/supabase/client";
import type { Job, UserState } from "@/lib/types";

type Filters = {
  q: string;
  minScore: number;
  category: string;
  kind: string;
  source: string;
  notApplied: boolean;
  last24h: boolean;
  showHidden: boolean;
  showClosed: boolean;
  sort: "score" | "new";
};

const DEFAULT_FILTERS: Filters = {
  q: "", minScore: 50, category: "", kind: "", source: "",
  notApplied: false, last24h: false, showHidden: false, showClosed: false, sort: "score",
};

const TONE_CLASSES = {
  good: "bg-good-soft text-good",
  warn: "bg-warn-soft text-warn",
  bad: "bg-bad-soft text-bad",
  none: "bg-surface-2 text-muted",
};
const DAY = 24 * 3600 * 1000;

function ScoreBadge({ score }: { score: number | null }) {
  return (
    <span className={`inline-flex h-9 w-11 shrink-0 items-center justify-center rounded-lg text-base font-bold ${TONE_CLASSES[scoreTone(score)]}`}>
      {score ?? "–"}
    </span>
  );
}

function sources(job: Job): string[] {
  return [...new Set(job.job_sources.map((s) => SOURCE_NAMES[s.source] ?? s.source))].sort();
}

function workplace(job: Job): string {
  if (job.is_remote) return "Remote";
  if (job.is_hybrid) return "Hybrid";
  return "";
}

function link(job: Job): string | null {
  return safeUrl(job.canonical_url) || safeUrl(job.url);
}

export default function JobFeed({ initialJobs }: { initialJobs: Job[] }) {
  const [jobs, setJobs] = useState(initialJobs);
  const [filters, setFilters] = useState(DEFAULT_FILTERS);
  const [expanded, setExpanded] = useState<number | null>(null);
  const [askReason, setAskReason] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [now] = useState(() => Date.now());
  const supabase = useMemo(() => createClient(), []);

  const set = <K extends keyof Filters>(key: K, value: Filters[K]) => setFilters((f) => ({ ...f, [key]: value }));

  const categories = useMemo(
    () => [...new Set(jobs.map((j) => j.role_category).filter(Boolean) as string[])].sort(),
    [jobs],
  );
  const sourceOptions = useMemo(() => [...new Set(jobs.flatMap((j) => j.job_sources.map((s) => s.source)))].sort(), [jobs]);

  const visible = useMemo(() => {
    const q = filters.q.trim().toLowerCase();
    const list = jobs.filter((j) => {
      if (!filters.showClosed && j.status === "closed") return false;
      if (!filters.showHidden && j.user_state === "not_relevant") return false;
      if ((j.match_score ?? 0) < filters.minScore) return false;
      if (filters.category && j.role_category !== filters.category) return false;
      if (filters.kind && j.companies?.kind !== filters.kind) return false;
      if (filters.source && !j.job_sources.some((s) => s.source === filters.source)) return false;
      if (filters.notApplied && j.user_state === "applied") return false;
      if (filters.last24h && now - new Date(j.first_seen_at).getTime() > DAY) return false;
      if (q && !`${j.title} ${j.companies?.name ?? ""} ${j.location ?? ""}`.toLowerCase().includes(q)) return false;
      return true;
    });
    return list.sort((a, b) =>
      filters.sort === "new"
        ? new Date(b.first_seen_at).getTime() - new Date(a.first_seen_at).getTime()
        : (b.match_score ?? -1) - (a.match_score ?? -1),
    );
  }, [jobs, filters, now]);

  const stats = useMemo(() => {
    const open = jobs.filter((j) => j.status === "open");
    return {
      open: open.length,
      today: open.filter((j) => now - new Date(j.first_seen_at).getTime() <= DAY).length,
      strong: open.filter((j) => (j.match_score ?? 0) >= 75 && j.user_state === "new").length,
      applied: jobs.filter((j) => j.user_state === "applied").length,
    };
  }, [jobs, now]);

  async function act(job: Job, state: UserState, reason: string | null = null) {
    const before = jobs;
    setError(null);
    setAskReason(null);
    setJobs((list) => list.map((j) => (j.id === job.id ? { ...j, user_state: state, not_relevant_reason: reason } : j)));
    try {
      await setJobState(supabase, job.id, state, reason);
    } catch (e) {
      setJobs(before);
      setError(`Couldn't update: ${(e as Error).message}`);
    }
  }

  if (jobs.length === 0) {
    return (
      <div className="rounded-2xl border border-dashed border-border p-10 text-center">
        <p className="text-lg font-semibold">Your first matches are on the way</p>
        <p className="mt-2 text-sm text-muted">
          FirstIn checks new jobs every hour. Matching roles will appear here — and on Telegram.
        </p>
      </div>
    );
  }

  return (
    <div>
      <div className="mb-5 grid grid-cols-2 gap-3 sm:grid-cols-4">
        {[
          ["Open jobs", stats.open],
          ["New in 24h", stats.today],
          ["Strong matches to review", stats.strong],
          ["Applied", stats.applied],
        ].map(([label, value]) => (
          <div key={label} className="rounded-xl border border-border bg-surface px-4 py-3">
            <div className="text-2xl font-bold">{value}</div>
            <div className="text-xs text-muted">{label}</div>
          </div>
        ))}
      </div>

      <div className="mb-4 rounded-xl border border-border bg-surface p-3">
        <div className="flex flex-wrap items-center gap-2">
          <input
            placeholder="Search role, company, city…"
            value={filters.q}
            onChange={(e) => set("q", e.target.value)}
            className="min-w-0 flex-1 basis-48 rounded-lg border border-border bg-bg px-3 py-1.5 text-sm outline-none focus:border-accent"
          />
          <label className="flex items-center gap-2 text-sm">
            <span className="text-muted">Score from</span>
            <input type="range" min={0} max={100} step={5} value={filters.minScore}
              onChange={(e) => set("minScore", Number(e.target.value))} className="w-24 accent-[var(--accent)]" />
            <span className="w-7 font-semibold">{filters.minScore}</span>
          </label>
          <select value={filters.sort} onChange={(e) => set("sort", e.target.value as Filters["sort"])}
            className="rounded-lg border border-border bg-bg px-2 py-1.5 text-sm">
            <option value="score">Best match</option>
            <option value="new">Newest</option>
          </select>
        </div>
        <div className="mt-2 flex flex-wrap items-center gap-2 text-sm">
          <select value={filters.category} onChange={(e) => set("category", e.target.value)}
            className="rounded-lg border border-border bg-bg px-2 py-1">
            <option value="">All categories</option>
            {categories.map((c) => <option key={c} value={c}>{c}</option>)}
          </select>
          <select value={filters.kind} onChange={(e) => set("kind", e.target.value)}
            className="rounded-lg border border-border bg-bg px-2 py-1">
            <option value="">All companies</option>
            <option value="startup">Startups</option>
            <option value="enterprise">Large companies</option>
          </select>
          <select value={filters.source} onChange={(e) => set("source", e.target.value)}
            className="rounded-lg border border-border bg-bg px-2 py-1">
            <option value="">All sources</option>
            {sourceOptions.map((s) => <option key={s} value={s}>{SOURCE_NAMES[s] ?? s}</option>)}
          </select>
          {([
            ["notApplied", "Not applied yet"],
            ["last24h", "New in 24h"],
            ["showHidden", "Show hidden"],
            ["showClosed", "Show closed"],
          ] as const).map(([key, label]) => (
            <label key={key} className={`cursor-pointer select-none rounded-full border px-3 py-1 transition ${
              filters[key] ? "border-accent bg-accent-soft text-accent" : "border-border text-muted hover:text-text"}`}>
              <input type="checkbox" className="sr-only" checked={filters[key]} onChange={(e) => set(key, e.target.checked)} />
              {label}
            </label>
          ))}
          {JSON.stringify(filters) !== JSON.stringify(DEFAULT_FILTERS) && (
            <button onClick={() => setFilters(DEFAULT_FILTERS)} className="text-accent hover:underline">Reset</button>
          )}
        </div>
      </div>

      {error && <p className="mb-3 rounded-lg bg-bad-soft px-3 py-2 text-sm text-bad">{error}</p>}
      <p className="mb-2 text-sm text-muted">Showing {visible.length} jobs</p>

      <ul className="space-y-2">
        {visible.map((job) => {
          const open = expanded === job.id;
          const dim = job.user_state === "not_relevant" || job.status === "closed";
          return (
            <li key={job.id} className={`rounded-xl border border-border bg-surface transition ${dim ? "opacity-60" : ""}`}>
              <div className="flex items-start gap-3 p-3">
                <ScoreBadge score={job.match_score} />
                <button onClick={() => setExpanded(open ? null : job.id)} className="min-w-0 flex-1 text-start">
                  <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                    <span dir="auto" className="font-semibold leading-snug">{job.title}</span>
                    {job.user_state !== "new" && (
                      <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${
                        job.user_state === "applied" ? "bg-good-soft text-good"
                          : job.user_state === "saved" ? "bg-accent-soft text-accent" : "bg-surface-2 text-muted"}`}>
                        {STATE_LABEL[job.user_state]}{job.not_relevant_reason ? ` · ${job.not_relevant_reason}` : ""}
                      </span>
                    )}
                    {job.status === "closed" && <span className="rounded-full bg-surface-2 px-2 py-0.5 text-xs text-muted">Closed</span>}
                  </div>
                  <div className="mt-0.5 text-sm text-muted">
                    <span dir="auto">{job.companies?.name}</span>
                    {" · "}{job.location ?? "Location unknown"}{workplace(job) && ` · ${workplace(job)}`}
                    {job.job_type && job.job_type !== "other" && ` · ${JOB_TYPE_LABEL[job.job_type]}`}
                  </div>
                  <div className="mt-0.5 text-xs text-muted">
                    {job.role_category && <span dir="auto">{job.role_category} · </span>}
                    {sources(job).join(" + ")} · {timeAgo(job.first_seen_at, now)}
                  </div>
                </button>
                <div className="hidden shrink-0 gap-1 sm:flex">
                  <Actions job={job} onAct={act} onAskReason={() => setAskReason(askReason === job.id ? null : job.id)} />
                </div>
              </div>

              <div className="flex gap-1 px-3 pb-3 sm:hidden">
                <Actions job={job} onAct={act} onAskReason={() => setAskReason(askReason === job.id ? null : job.id)} />
              </div>

              {askReason === job.id && (
                <div className="flex flex-wrap items-center gap-2 border-t border-border px-3 py-2 text-sm">
                  <span className="text-muted">Why not?</span>
                  {NOT_RELEVANT_REASONS.map((r) => (
                    <button key={r} onClick={() => act(job, "not_relevant", r)}
                      className="rounded-full border border-border px-3 py-1 hover:border-accent hover:text-accent">{r}</button>
                  ))}
                </div>
              )}

              {open && (
                <div className="space-y-2 border-t border-border px-3 py-3 text-sm">
                  {job.match_reasons.map((r, i) => <p key={`r${i}`} dir="auto">✅ {r}</p>)}
                  {job.red_flags.map((r, i) => <p key={`f${i}`} dir="auto" className="text-warn">⚠️ {r}</p>)}
                  {job.requirements.length > 0 && (
                    <div className="flex flex-wrap gap-1 pt-1">
                      {job.requirements.map((r) => (
                        <span key={r} className="rounded-md bg-surface-2 px-2 py-0.5 text-xs">{r}</span>
                      ))}
                    </div>
                  )}
                  {link(job) && (
                    <a href={link(job)!} target="_blank" rel="noreferrer"
                      className="inline-block pt-1 font-medium text-accent hover:underline">Open the job ↗</a>
                  )}
                </div>
              )}
            </li>
          );
        })}
      </ul>
      {visible.length === 0 && (
        <p className="rounded-xl border border-dashed border-border p-8 text-center text-muted">
          No jobs match these filters. Try lowering the score.
        </p>
      )}
    </div>
  );
}

function Actions({ job, onAct, onAskReason }: {
  job: Job;
  onAct: (job: Job, state: UserState) => void;
  onAskReason: () => void;
}) {
  const btn = "rounded-lg border border-border px-2.5 py-1 text-sm transition hover:border-accent hover:text-accent";
  if (job.user_state !== "new") {
    return <button className={btn} onClick={() => onAct(job, "new")}>Undo</button>;
  }
  return (
    <>
      {link(job) && <a href={link(job)!} target="_blank" rel="noreferrer" className={btn}>🔗 Open</a>}
      <button className={btn} onClick={() => onAct(job, "applied")}>✅ Applied</button>
      <button className={btn} onClick={() => onAct(job, "saved")}>⭐ Save</button>
      <button className={btn} onClick={onAskReason}>👎 Not for me</button>
    </>
  );
}
