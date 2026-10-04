"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import AuthCard, { MIN_PASSWORD, buttonClass, inputClass } from "@/components/AuthCard";
import { createClient } from "@/lib/supabase/client";

/** Reached from the password-reset email (the link signs the user in first). */
export default function ResetPasswordPage() {
  const router = useRouter();
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (password.length < MIN_PASSWORD) return setError(`Use at least ${MIN_PASSWORD} characters.`);
    if (password !== confirm) return setError("The passwords don't match.");
    setBusy(true);
    setError(null);
    const { error } = await createClient().auth.updateUser({ password });
    setBusy(false);
    if (error) return setError("Couldn't update the password. Request a new link and try again.");
    router.replace("/dashboard");
    router.refresh();
  }

  return (
    <AuthCard title="Choose a new password">
      <form onSubmit={onSubmit}>
        <label className="mb-1 block text-sm font-medium" htmlFor="password">New password (at least {MIN_PASSWORD} characters)</label>
        <input id="password" type="password" autoComplete="new-password" required
          value={password} onChange={(e) => setPassword(e.target.value)} className={inputClass} />
        <label className="mb-1 block text-sm font-medium" htmlFor="confirm">Confirm password</label>
        <input id="confirm" type="password" autoComplete="new-password" required
          value={confirm} onChange={(e) => setConfirm(e.target.value)} className={inputClass} />
        {error && <p className="mb-4 rounded-lg bg-bad-soft px-3 py-2 text-sm text-bad">{error}</p>}
        <button type="submit" disabled={busy} className={buttonClass}>{busy ? "Saving…" : "Save password"}</button>
      </form>
    </AuthCard>
  );
}
