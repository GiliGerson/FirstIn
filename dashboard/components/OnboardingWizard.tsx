"use client";

import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";
import TelegramConnect from "@/components/TelegramConnect";
import {
  CITY_GROUPS, DEFAULT_INCLUDE_KEYWORDS, DEFAULT_QUIET_HOURS, JOB_TYPE_OPTIONS, LANGUAGE_OPTIONS, ROLE_OPTIONS,
  YEAR_OPTIONS,
} from "@/lib/onboarding";
import { createClient } from "@/lib/supabase/client";
import type { Profile } from "@/lib/types";

const STEPS = ["About you", "What you're looking for", "Where", "Telegram"];

function Chip({ on, onClick, children }: { on: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button type="button" onClick={onClick}
      className={`rounded-full border px-3 py-1.5 text-sm transition ${
        on ? "border-accent bg-accent-soft font-medium text-accent" : "border-border hover:border-accent"}`}>
      {children}
    </button>
  );
}

function toggle<T>(list: T[], item: T): T[] {
  return list.includes(item) ? list.filter((x) => x !== item) : [...list, item];
}

export default function OnboardingWizard({ profile, botUsername }: { profile: Profile; botUsername?: string }) {
  const router = useRouter();
  const supabase = useMemo(() => createClient(), []);
  const [step, setStep] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  // step 1
  const [name, setName] = useState(profile.display_name ?? "");
  const [field, setField] = useState(profile.field_of_study ?? "");
  const [year, setYear] = useState<number | null>(profile.study_year);
  const [languages, setLanguages] = useState<string[]>(profile.languages?.length ? profile.languages : ["English", "Hebrew"]);
  // step 2
  const [roles, setRoles] = useState<string[]>([]);
  const [customRole, setCustomRole] = useState("");
  const [jobTypes, setJobTypes] = useState<string[]>(["student", "internship"]);
  const [days, setDays] = useState(3);
  // step 3
  const [cities, setCities] = useState<string[]>([]);
  const [hybrid, setHybrid] = useState(true);
  const [remote, setRemote] = useState(true);

  function validate(): string | null {
    if (step === 0 && (!name.trim() || !field.trim() || !year)) return "Please fill in your name, field of study and year.";
    if (step === 1 && roles.length === 0) return "Pick at least one role.";
    if (step === 1 && jobTypes.length === 0) return "Pick at least one job type.";
    if (step === 2 && cities.length === 0 && !remote) return "Pick at least one city, or allow remote work.";
    return null;
  }

  async function saveAndNext() {
    const problem = validate();
    if (problem) return setError(problem);
    setError(null);
    if (step < 2) return setStep(step + 1);
    if (step === 2) {
      setBusy(true);
      const ok = await saveProfileAndSettings();
      setBusy(false);
      if (ok) setStep(3);
    }
  }

  async function saveProfileAndSettings(): Promise<boolean> {
    const { error: profileError } = await supabase.from("profiles").update({
      display_name: name.trim(), field_of_study: field.trim(), study_year: year, languages,
    }).eq("user_id", profile.user_id);
    if (profileError) {
      setError(`Couldn't save your profile: ${profileError.message}`);
      return false;
    }
    const preferences = {
      roles, job_types: jobTypes, max_days_per_week: days, locations: cities,
      accept_hybrid: hybrid, accept_remote: remote,
    };
    const { data: existing } = await supabase.from("search_settings").select("id").eq("is_active", true).maybeSingle();
    const { error: settingsError } = existing
      ? await supabase.from("search_settings").update(preferences).eq("id", existing.id)
      : await supabase.from("search_settings").insert({
          ...preferences, preset_name: "default", is_active: true,
          include_keywords: DEFAULT_INCLUDE_KEYWORDS, exclude_keywords: [],
          instant_threshold: 75, digest_threshold: 50, quiet_hours: DEFAULT_QUIET_HOURS,
        });
    if (settingsError) {
      setError(`Couldn't save your preferences: ${settingsError.message}`);
      return false;
    }
    return true;
  }

  async function finish() {
    setBusy(true);
    const { error } = await supabase.from("profiles").update({ onboarding_done: true }).eq("user_id", profile.user_id);
    setBusy(false);
    if (error) return setError(`Couldn't finish: ${error.message}`);
    router.replace("/dashboard");
    router.refresh();
  }

  const input = "w-full rounded-lg border border-border bg-bg px-3 py-2 outline-none focus:border-accent";
  return (
    <main className="mx-auto max-w-2xl px-4 py-10">
      <div className="mb-8 flex items-center gap-3">
        <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-accent font-bold text-white">F</span>
        <div>
          <h1 className="text-xl font-bold">Set up FirstIn</h1>
          <p className="text-sm text-muted">Step {step + 1} of {STEPS.length} · {STEPS[step]}</p>
        </div>
      </div>
      <div className="mb-6 flex gap-1.5">
        {STEPS.map((s, i) => (
          <span key={s} className={`h-1.5 flex-1 rounded-full ${i <= step ? "bg-accent" : "bg-surface-2"}`} />
        ))}
      </div>

      <section className="rounded-2xl border border-border bg-surface p-6">
        {step === 0 && (
          <div className="space-y-5">
            <div>
              <label className="mb-1 block text-sm font-medium">First name</label>
              <input value={name} onChange={(e) => setName(e.target.value)} className={input} />
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium">What do you study?</label>
              <input value={field} onChange={(e) => setField(e.target.value)} className={input}
                placeholder="e.g. Computer Science, Industrial Engineering" />
            </div>
            <div>
              <p className="mb-2 text-sm font-medium">Year</p>
              <div className="flex flex-wrap gap-2">
                {YEAR_OPTIONS.map((y) => (
                  <Chip key={y.value} on={year === y.value} onClick={() => setYear(y.value)}>{y.label}</Chip>
                ))}
              </div>
            </div>
            <div>
              <p className="mb-2 text-sm font-medium">Languages you work in</p>
              <div className="flex flex-wrap gap-2">
                {LANGUAGE_OPTIONS.map((l) => (
                  <Chip key={l} on={languages.includes(l)} onClick={() => setLanguages(toggle(languages, l))}>{l}</Chip>
                ))}
              </div>
            </div>
          </div>
        )}

        {step === 1 && (
          <div className="space-y-6">
            <div>
              <p className="text-sm font-medium">Roles you want</p>
              <p className="mb-2 text-xs text-muted">Tap in order of priority — your first pick counts most.</p>
              <div className="flex flex-wrap gap-2">
                {[...ROLE_OPTIONS, ...roles.filter((r) => !ROLE_OPTIONS.includes(r))].map((r) => (
                  <Chip key={r} on={roles.includes(r)} onClick={() => setRoles(toggle(roles, r))}>
                    {roles.includes(r) && <span className="me-1 font-bold">{roles.indexOf(r) + 1}</span>}{r}
                  </Chip>
                ))}
              </div>
              <div className="mt-3 flex gap-2">
                <input value={customRole} onChange={(e) => setCustomRole(e.target.value)} placeholder="Add another role…"
                  className={input} onKeyDown={(e) => {
                    if (e.key === "Enter" && customRole.trim()) {
                      e.preventDefault();
                      setRoles([...roles, customRole.trim()]);
                      setCustomRole("");
                    }
                  }} />
              </div>
            </div>
            <div>
              <p className="mb-2 text-sm font-medium">Job types</p>
              <div className="flex flex-wrap gap-2">
                {JOB_TYPE_OPTIONS.map((t) => (
                  <Chip key={t.value} on={jobTypes.includes(t.value)} onClick={() => setJobTypes(toggle(jobTypes, t.value))}>
                    {t.label}
                  </Chip>
                ))}
              </div>
            </div>
            <div>
              <p className="mb-2 text-sm font-medium">Days a week you can work: <b>{days}</b></p>
              <input type="range" min={1} max={5} value={days} onChange={(e) => setDays(Number(e.target.value))}
                className="w-full accent-[var(--accent)]" />
            </div>
          </div>
        )}

        {step === 2 && (
          <div className="space-y-5">
            {CITY_GROUPS.map((group) => (
              <div key={group.label}>
                <div className="mb-2 flex items-center justify-between">
                  <p className="text-sm font-medium">{group.label}</p>
                  <button type="button" className="text-xs text-accent hover:underline"
                    onClick={() => setCities(group.cities.every((c) => cities.includes(c))
                      ? cities.filter((c) => !group.cities.includes(c))
                      : [...new Set([...cities, ...group.cities])])}>
                    {group.cities.every((c) => cities.includes(c)) ? "Clear" : "Select all"}
                  </button>
                </div>
                <div className="flex flex-wrap gap-2">
                  {group.cities.map((c) => (
                    <Chip key={c} on={cities.includes(c)} onClick={() => setCities(toggle(cities, c))}>{c}</Chip>
                  ))}
                </div>
              </div>
            ))}
            <div className="flex flex-wrap gap-2 border-t border-border pt-4">
              <Chip on={hybrid} onClick={() => setHybrid(!hybrid)}>Hybrid is fine</Chip>
              <Chip on={remote} onClick={() => setRemote(!remote)}>Remote is fine</Chip>
            </div>
          </div>
        )}

        {step === 3 && (
          <div className="space-y-4">
            <p className="leading-relaxed">
              Matching jobs are sent to you on Telegram. Connect it now — it takes one tap.
            </p>
            <TelegramConnect connected={Boolean(profile.telegram_chat_id)} botUsername={botUsername} />
            <p className="text-xs text-muted">You can also connect later from your dashboard.</p>
          </div>
        )}

        {error && <p className="mt-5 rounded-lg bg-bad-soft px-3 py-2 text-sm text-bad">{error}</p>}

        <div className="mt-6 flex items-center justify-between">
          {step > 0 ? (
            <button onClick={() => { setError(null); setStep(step - 1); }} className="text-sm text-muted hover:text-text">← Back</button>
          ) : <span />}
          {step < 3 ? (
            <button onClick={saveAndNext} disabled={busy}
              className="rounded-lg bg-accent px-5 py-2.5 font-semibold text-white hover:opacity-90 disabled:opacity-60">
              {busy ? "Saving…" : "Continue"}
            </button>
          ) : (
            <button onClick={finish} disabled={busy}
              className="rounded-lg bg-accent px-5 py-2.5 font-semibold text-white hover:opacity-90 disabled:opacity-60">
              {busy ? "Finishing…" : "Finish"}
            </button>
          )}
        </div>
      </section>
    </main>
  );
}
