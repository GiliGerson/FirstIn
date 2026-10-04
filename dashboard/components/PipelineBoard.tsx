"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { setApplicationStage, updateApplication } from "@/lib/actions";
import { CLOSED_STAGES, STAGES, STAGE_LABEL, formatDate, timeAgo } from "@/lib/labels";
import { pipelineStats } from "@/lib/pipelineStats";
import { safeUrl } from "@/lib/safeUrl";
import { createClient } from "@/lib/supabase/client";
import type { Application, ApplicationFields, Stage } from "@/lib/types";

const ALL_STAGES: Stage[] = [...STAGES, ...CLOSED_STAGES];
const COLUMNS: { key: string; label: string; stages: readonly Stage[] }[] = [
  ...STAGES.map((s) => ({ key: s, label: STAGE_LABEL[s], stages: [s] as const })),
  { key: "closed", label: "Closed", stages: CLOSED_STAGES },
];
const DAY = 24 * 3600 * 1000;

function daysSince(iso: string, now: number) {
  return Math.max(0, Math.floor((now - new Date(iso).getTime()) / DAY));
}

export default function PipelineBoard({ initialApps }: { initialApps: Application[] }) {
  const [apps, setApps] = useState(initialApps);
  const [openId, setOpenId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [now] = useState(() => Date.now());
  const supabase = useMemo(() => createClient(), []);
  const stats = useMemo(() => pipelineStats(apps, now), [apps, now]);

  async function move(app: Application, to: Stage) {
    if (to === app.stage) return;
    const before = apps;
    const event = {
      id: -Date.now(), type: "stage_change", occurred_at: new Date().toISOString(),
      payload: { from: app.stage, to, via: "dashboard" },
    };
    setError(null);
    setApps((list) => list.map((a) => (a.id === app.id ? { ...a, stage: to, events: [...a.events, event] } : a)));
    try {
      await setApplicationStage(supabase, app.id, app.stage, to);
    } catch (e) {
      setApps(before);
      setError(`Couldn't update: ${(e as Error).message}`);
    }
  }

  async function save(app: Application, fields: Partial<ApplicationFields>) {
    setError(null);
    setApps((list) => list.map((a) => (a.id === app.id ? { ...a, ...fields } : a)));
    try {
      await updateApplication(supabase, app.id, fields);
    } catch (e) {
      setError(`Couldn't save: ${(e as Error).message}`);
    }
  }

  const open = apps.find((a) => a.id === openId) ?? null;

  if (apps.length === 0) {
    return (
      <div className="rounded-2xl border border-dashed border-border p-10 text-center">
        <p className="text-lg font-semibold">No applications yet</p>
        <p className="mt-2 text-sm text-muted">
          Mark a job as &quot;Applied&quot; — here or on Telegram — and it shows up here as a card.
        </p>
        <Link href="/dashboard" className="mt-4 inline-block font-medium text-accent hover:underline">Browse jobs →</Link>
      </div>
    );
  }

  return (
    <div>
      <div className="mb-5 grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Stat label="Applied this week" value={stats.thisWeek} hint={`${stats.total} total`} />
        <Stat label="Response rate" value={stats.responseRate === null ? "–" : `${stats.responseRate}%`} />
        <Stat label="Avg. days to reply"
          value={stats.avgDaysToResponse === null ? "–" : stats.avgDaysToResponse} />
        <Stat label="Follow-ups due" value={stats.followupsDue} warn={stats.followupsDue > 0} />
      </div>

      {stats.byCategory.length > 0 && (
        <div className="mb-5 flex flex-wrap items-center gap-2 text-sm">
          <span className="text-muted">By category:</span>
          {stats.byCategory.map(([category, count]) => (
            <span key={category} className="rounded-full bg-surface-2 px-3 py-1">
              <span dir="auto">{category}</span> · <span className="ltr font-semibold">{count}</span>
            </span>
          ))}
        </div>
      )}

      {error && <p className="mb-3 rounded-lg bg-bad-soft px-3 py-2 text-sm text-bad">{error}</p>}

      <div className="-mx-4 flex snap-x gap-3 overflow-x-auto px-4 pb-3 lg:mx-0 lg:grid lg:grid-cols-6 lg:overflow-visible lg:px-0">
        {COLUMNS.map((col) => {
          const cards = apps.filter((a) => col.stages.includes(a.stage));
          return (
            <section key={col.key} className="w-64 shrink-0 snap-start rounded-xl bg-surface-2 p-2 lg:w-auto">
              <h2 className="mb-2 flex items-center justify-between px-1 text-sm font-semibold">
                {col.label}
                <span className="ltr rounded-full bg-surface px-2 text-xs text-muted">{cards.length}</span>
              </h2>
              <ul className="space-y-2">
                {cards.map((app) => {
                  const due = app.next_followup_at && new Date(app.next_followup_at).getTime() <= now;
                  return (
                    <li key={app.id}>
                      <button onClick={() => setOpenId(app.id)}
                        className="w-full rounded-lg border border-border bg-surface p-3 text-start transition hover:border-accent">
                        <div dir="auto" className="text-sm font-semibold leading-snug">{app.jobs?.title ?? "Job"}</div>
                        <div dir="auto" className="mt-0.5 text-xs text-muted">{app.jobs?.companies?.name}</div>
                        <div className="mt-2 flex flex-wrap items-center gap-1 text-xs">
                          <span className="text-muted">{daysSince(app.applied_at, now)}d ago</span>
                          {col.key === "closed" && (
                            <span className="rounded-full bg-surface-2 px-2">{STAGE_LABEL[app.stage]}</span>
                          )}
                          {due && <span className="rounded-full bg-warn-soft px-2 text-warn">follow-up</span>}
                          {app.emails.length > 0 && <span className="text-muted">📬 {app.emails.length}</span>}
                        </div>
                      </button>
                    </li>
                  );
                })}
              </ul>
            </section>
          );
        })}
      </div>

      {open && (
        <ApplicationPanel key={open.id} app={open} now={now} onClose={() => setOpenId(null)} onMove={move} onSave={save} />
      )}
    </div>
  );
}

function Stat({ label, value, hint, warn }: { label: string; value: string | number; hint?: string; warn?: boolean }) {
  return (
    <div className={`rounded-xl border px-4 py-3 ${warn ? "border-warn bg-warn-soft" : "border-border bg-surface"}`}>
      <div className="ltr text-end text-2xl font-bold">{value}</div>
      <div className="text-xs text-muted">{label}{hint && ` · ${hint}`}</div>
    </div>
  );
}

function ApplicationPanel({ app, now, onClose, onMove, onSave }: {
  app: Application;
  now: number;
  onClose: () => void;
  onMove: (app: Application, to: Stage) => void;
  onSave: (app: Application, fields: Partial<ApplicationFields>) => void;
}) {
  const [notes, setNotes] = useState(app.notes ?? "");
  const [contactName, setContactName] = useState(app.contact_name ?? "");
  const [contactEmail, setContactEmail] = useState(app.contact_email ?? "");
  const [followup, setFollowup] = useState(app.next_followup_at?.slice(0, 10) ?? "");
  const link = safeUrl(app.jobs?.canonical_url) || safeUrl(app.jobs?.url);
  const history = [...app.events].sort((a, b) => a.occurred_at.localeCompare(b.occurred_at));

  function saveDetails() {
    onSave(app, {
      notes: notes || null,
      contact_name: contactName || null,
      contact_email: contactEmail || null,
      next_followup_at: followup ? new Date(`${followup}T09:00:00`).toISOString() : null,
    });
    onClose();
  }

  const input = "w-full rounded-lg border border-border bg-bg px-3 py-1.5 text-sm outline-none focus:border-accent";
  return (
    <div className="fixed inset-0 z-30 flex justify-end bg-black/30" onClick={onClose}>
      <aside onClick={(e) => e.stopPropagation()}
        className="h-full w-full max-w-md overflow-y-auto bg-surface p-5 shadow-xl">
        <div className="mb-4 flex items-start justify-between gap-3">
          <div>
            <h2 dir="auto" className="text-lg font-bold leading-snug">{app.jobs?.title}</h2>
            <p dir="auto" className="text-sm text-muted">
              {app.jobs?.companies?.name}{app.jobs?.location && ` · ${app.jobs.location}`}
            </p>
            <p className="mt-1 text-xs text-muted">
              Applied {formatDate(app.applied_at)} ({timeAgo(app.applied_at, now)})
            </p>
          </div>
          <button onClick={onClose} className="rounded-lg px-2 text-xl text-muted hover:text-text" aria-label="Close">×</button>
        </div>

        <label className="mb-1 block text-sm font-medium">Stage</label>
        <div className="mb-4 flex flex-wrap gap-1">
          {ALL_STAGES.map((s) => (
            <button key={s} onClick={() => onMove(app, s)}
              className={`rounded-full border px-3 py-1 text-sm transition ${
                app.stage === s ? "border-accent bg-accent-soft text-accent" : "border-border hover:border-accent"}`}>
              {STAGE_LABEL[s]}
            </button>
          ))}
        </div>

        <div className="space-y-3">
          <div>
            <label className="mb-1 block text-sm font-medium">Follow-up date</label>
            <input type="date" value={followup} onChange={(e) => setFollowup(e.target.value)} className={input} />
          </div>
          <div className="grid grid-cols-2 gap-2">
            <div>
              <label className="mb-1 block text-sm font-medium">Contact</label>
              <input value={contactName} onChange={(e) => setContactName(e.target.value)} className={input} />
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium">Email</label>
              <input type="email" dir="ltr" value={contactEmail} onChange={(e) => setContactEmail(e.target.value)} className={input} />
            </div>
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium">Notes</label>
            <textarea rows={4} value={notes} onChange={(e) => setNotes(e.target.value)} className={input}
              placeholder="Who you talked to, what they asked, what to send…" />
          </div>
          <div className="flex items-center gap-3">
            <button onClick={saveDetails} className="rounded-lg bg-accent px-4 py-2 text-sm font-semibold text-white hover:opacity-90">
              Save
            </button>
            {link && <a href={link} target="_blank" rel="noreferrer" className="text-sm text-accent hover:underline">Open the job ↗</a>}
          </div>
        </div>

        {app.emails.length > 0 && (
          <div className="mt-6">
            <h3 className="mb-2 text-sm font-semibold">Linked emails</h3>
            <ul className="space-y-2 text-sm">
              {app.emails.map((m) => (
                <li key={m.id} className="rounded-lg bg-surface-2 p-2">
                  <div dir="auto" className="font-medium">{m.subject}</div>
                  {m.summary && <div className="text-muted">{m.summary}</div>}
                </li>
              ))}
            </ul>
          </div>
        )}

        <div className="mt-6">
          <h3 className="mb-2 text-sm font-semibold">History</h3>
          <ol className="space-y-1 border-s-2 border-border ps-3 text-sm">
            {history.map((e) => (
              <li key={e.id}>
                <span className="text-muted">{formatDate(e.occurred_at)} · </span>
                {e.type === "applied" ? "Applied" : e.type === "stage_change"
                  ? `${STAGE_LABEL[String(e.payload.from)] ?? e.payload.from} → ${STAGE_LABEL[String(e.payload.to)] ?? e.payload.to}`
                  : e.type}
                {e.payload?.via === "email" && " (from email)"}
              </li>
            ))}
          </ol>
        </div>
      </aside>
    </div>
  );
}
