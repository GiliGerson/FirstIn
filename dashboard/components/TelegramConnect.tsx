"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { createClient } from "@/lib/supabase/client";

const POLL_MS = 3000;
const POLL_FOR_MS = 10 * 60 * 1000;

/**
 * "Connect Telegram": creates a one-time code (RPC) and opens t.me/<bot>?start=<code>, then waits
 * for the bot to store the chat on the user's profile.
 *
 * Browsers block windows opened after an `await`, so the tab is opened synchronously on click and
 * pointed at Telegram once the code is ready. If it's still blocked, a big "Open Telegram" link is
 * shown instead. The bot username comes from the server at request time (no rebuild needed).
 */
export default function TelegramConnect({ connected: initiallyConnected, botUsername, onConnected }: {
  connected: boolean;
  botUsername: string | undefined;
  onConnected?: () => void;
}) {
  const supabase = useMemo(() => createClient(), []);
  const [connected, setConnected] = useState(initiallyConnected);
  const [waiting, setWaiting] = useState(false);
  const [link, setLink] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => () => { if (timer.current) clearInterval(timer.current); }, []);

  function startPolling() {
    if (timer.current) clearInterval(timer.current);
    const started = Date.now();
    timer.current = setInterval(async () => {
      const { data } = await supabase.from("profiles").select("telegram_chat_id").maybeSingle();
      if (data?.telegram_chat_id) {
        clearInterval(timer.current!);
        setWaiting(false);
        setConnected(true);
        onConnected?.();
      } else if (Date.now() - started > POLL_FOR_MS) {
        clearInterval(timer.current!);
        setWaiting(false);
      }
    }, POLL_MS);
  }

  async function connect() {
    setError(null);
    if (!botUsername) {
      setError("Telegram isn't configured yet. Please try again later.");
      return;
    }
    const tab = window.open("about:blank", "_blank");   // must happen synchronously on the click
    const { data: code, error } = await supabase.rpc("create_telegram_link_code");
    if (error || !code) {
      tab?.close();
      setError("Couldn't create a connection link. Please try again.");
      return;
    }
    const url = `https://t.me/${botUsername}?start=${code}`;
    setLink(url);
    if (tab && !tab.closed) tab.location.href = url;
    setWaiting(true);
    startPolling();
  }

  if (connected) {
    return <p className="rounded-xl bg-good-soft px-4 py-3 text-sm font-medium text-good">✅ Telegram connected</p>;
  }
  return (
    <div>
      {!link ? (
        <button onClick={connect}
          className="w-full rounded-xl bg-[#229ED9] px-4 py-3 font-semibold text-white hover:opacity-90">
          Connect Telegram
        </button>
      ) : (
        <a href={link} target="_blank" rel="noreferrer"
          className="block w-full rounded-xl bg-[#229ED9] px-4 py-3 text-center font-semibold text-white hover:opacity-90">
          Open Telegram
        </a>
      )}
      {waiting && (
        <p className="mt-3 text-sm leading-relaxed text-muted">
          In Telegram, press <b>Start</b> in the chat with the bot. This page updates by itself once you&apos;re connected.
        </p>
      )}
      {error && <p className="mt-3 rounded-lg bg-bad-soft px-3 py-2 text-sm text-bad">{error}</p>}
    </div>
  );
}
