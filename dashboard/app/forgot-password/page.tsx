"use client";

import Link from "next/link";
import { useState } from "react";
import AuthCard, { buttonClass, inputClass } from "@/components/AuthCard";
import { createClient } from "@/lib/supabase/client";

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [sent, setSent] = useState(false);
  const [busy, setBusy] = useState(false);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    // Same answer whether or not the email exists, so the page can't be used to probe accounts
    await createClient().auth.resetPasswordForEmail(email, {
      redirectTo: `${window.location.origin}/auth/confirm?next=/reset-password`,
    });
    setBusy(false);
    setSent(true);
  }

  return (
    <AuthCard title="Reset your password" subtitle="We'll email you a link">
      {sent ? (
        <p className="text-sm leading-relaxed">
          If <span className="font-medium">{email}</span> has an account, a reset link is on its way. Open it in this
          browser to choose a new password.
        </p>
      ) : (
        <form onSubmit={onSubmit}>
          <label className="mb-1 block text-sm font-medium" htmlFor="email">Email</label>
          <input id="email" type="email" autoComplete="email" required
            value={email} onChange={(e) => setEmail(e.target.value)} className={inputClass} />
          <button type="submit" disabled={busy} className={buttonClass}>{busy ? "Sending…" : "Send reset link"}</button>
        </form>
      )}
      <Link href="/login" className="mt-5 inline-block text-sm font-medium text-accent hover:underline">Back to sign in</Link>
    </AuthCard>
  );
}
