"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const LINKS = [
  { href: "/dashboard", label: "Jobs" },
  { href: "/dashboard/pipeline", label: "Applications" },
  { href: "/dashboard/settings", label: "Search settings" },
];

export default function Nav() {
  const pathname = usePathname();
  return (
    <nav className="flex gap-1 overflow-x-auto">
      {LINKS.map(({ href, label }) => {
        const active = href === "/dashboard" ? pathname === "/dashboard" : pathname.startsWith(href);
        return (
          <Link
            key={href}
            href={href}
            className={`whitespace-nowrap rounded-lg px-3 py-1.5 text-sm font-medium transition ${
              active ? "bg-accent-soft text-accent" : "text-muted hover:bg-surface-2 hover:text-text"
            }`}
          >
            {label}
          </Link>
        );
      })}
    </nav>
  );
}
