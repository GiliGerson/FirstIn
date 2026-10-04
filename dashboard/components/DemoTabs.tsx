"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const TABS = [
  { href: "/demo", label: "Jobs" },
  { href: "/demo/applications", label: "Applications" },
  { href: "/demo/alerts", label: "Telegram alerts" },
];

export default function DemoTabs() {
  const pathname = usePathname();
  return (
    <nav className="flex gap-1 overflow-x-auto">
      {TABS.map(({ href, label }) => (
        <Link key={href} href={href}
          className={`whitespace-nowrap rounded-lg px-3 py-1.5 text-sm font-medium transition ${
            pathname === href ? "bg-accent-soft text-accent" : "text-muted hover:bg-surface-2 hover:text-text"}`}>
          {label}
        </Link>
      ))}
    </nav>
  );
}
