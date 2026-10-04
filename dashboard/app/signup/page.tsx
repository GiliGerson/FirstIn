"use client";

import Link from "next/link";
import { useState } from "react";
import AuthCard, { MIN_PASSWORD, buttonClass, inputClass } from "@/components/AuthCard";
import { createClient } from "@/lib/supabase/client";

export default function SignupPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [sent, setSent] = useState(false);
  const [busy, setBusy] = useState(false);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (password.length < MIN_PASSWORD) return setError(`Use at least ${MIN_PASSWORD} characters.`);
    if (password !== confirm) return setError("The passwords don't match.");
    setBusy(true);
    setError(null);
    const { error } = await createClient().auth.signUp({
      email,
      password,
      options: { emailRedirectTo: `${window.location.origin}/auth/confirm?next=/onboarding` },
    });
    setBusy(false);
    if (error) {
      setError(error.message.toLowerCase().includes("rate")
        ? "Too many attempts. Please try again in a few minutes."
        : "Sign-up didn't work. If you already have an account, try signing in.");
      return;
    }
    setSent(true);
  }

  if (sent) {
    return (
      <AuthCard title="Check your inbox 📬" subtitle="One last step">
        <p className="text-sm leading-relaxed">
          We sent a confirmation link to <span className="font-medium">{email}</span>. Open it to activate your
          account — ideally in this same browser.
        </p>
        <Link href="/login" className="mt-5 inline-block text-sm font-medium text-accent hover:underline">Back to sign in</Link>
      </AuthCard>
    );
  }

  return (
    <AuthCard title="Create your account" subtitle="Free · takes a minute">
      <form onSubmit={onSubmit}>
        <label className="mb-1 block text-sm font-medium" htmlFor="email">Email</label>
        <input id="email" type="email" autoComplete="email" required
          value={email} onChange={(e) => setEmail(e.target.value)} className={inputClass} />
        <label className="mb-1 block text-sm font-medium" htmlFor="password">Password (at least {MIN_PASSWORD} characters)</label>
        <input id="password" type="password" autoComplete="new-password" required
          value={password} onChange={(e) => setPassword(e.target.value)} className={inputClass} />
        <label className="mb-1 block text-sm font-medium" htmlFor="confirm">Confirm password</label>
        <input id="confirm" type="password" autoComplete="new-password" required
          value={confirm} onChange={(e) => setConfirm(e.target.value)} className={inputClass} />
        {error && <p className="mb-4 rounded-lg bg-bad-soft px-3 py-2 text-sm text-bad">{error}</p>}
        <button type="submit" disabled={busy} className={buttonClass}>{busy ? "Creating…" : "Create account"}</button>
        <p className="mt-5 text-center text-sm text-muted">
          Already have an account? <Link href="/login" className="font-medium text-accent hover:underline">Sign in</Link>
        </p>
      </form>
    </AuthCard>
  );
}
