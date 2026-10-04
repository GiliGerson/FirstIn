"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import AuthCard, { buttonClass, inputClass } from "@/components/AuthCard";
import { createClient } from "@/lib/supabase/client";

function LoginForm() {
  const router = useRouter();
  const params = useSearchParams();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(
    params.get("error") === "link" ? "That link is invalid or has expired. Please try again." : null,
  );
  const [busy, setBusy] = useState(false);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    const { error } = await createClient().auth.signInWithPassword({ email, password });
    setBusy(false);
    if (error) {
      setError(error.message.includes("not confirmed")
        ? "Please confirm your email first — check your inbox."
        : "Wrong email or password.");
      return;
    }
    router.replace("/dashboard");
    router.refresh();
  }

  return (
    <form onSubmit={onSubmit}>
      <label className="mb-1 block text-sm font-medium" htmlFor="email">Email</label>
      <input id="email" type="email" autoComplete="email" required
        value={email} onChange={(e) => setEmail(e.target.value)} className={inputClass} />
      <div className="mb-1 flex items-center justify-between">
        <label className="text-sm font-medium" htmlFor="password">Password</label>
        <Link href="/forgot-password" className="text-xs text-accent hover:underline">Forgot password?</Link>
      </div>
      <input id="password" type="password" autoComplete="current-password" required
        value={password} onChange={(e) => setPassword(e.target.value)} className={inputClass} />
      {error && <p className="mb-4 rounded-lg bg-bad-soft px-3 py-2 text-sm text-bad">{error}</p>}
      <button type="submit" disabled={busy} className={buttonClass}>{busy ? "Signing in…" : "Sign in"}</button>
      <p className="mt-5 text-center text-sm text-muted">
        New to FirstIn? <Link href="/signup" className="font-medium text-accent hover:underline">Create an account</Link>
      </p>
    </form>
  );
}

export default function LoginPage() {
  return (
    <AuthCard title="Welcome back" subtitle="Sign in to FirstIn">
      <Suspense>
        <LoginForm />
      </Suspense>
    </AuthCard>
  );
}
