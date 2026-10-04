import Link from "next/link";
import DemoTabs from "@/components/DemoTabs";

export const metadata = { title: "FirstIn — live demo" };

export default function DemoLayout({ children }: LayoutProps<"/demo">) {
  return (
    <div className="min-h-screen">
      <div className="bg-accent px-4 py-2 text-center text-sm font-medium text-white">
        Live demo with sample data — every company and job here is fictional.{" "}
        <Link href="/signup" className="underline underline-offset-2">Create your own account →</Link>
      </div>
      <header className="sticky top-0 z-20 border-b border-border bg-surface/90 backdrop-blur">
        <div className="mx-auto flex max-w-6xl items-center gap-4 px-4 py-3">
          <Link href="/" className="flex items-center gap-2 font-bold">
            <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-accent text-sm text-white">F</span>
            <span className="hidden sm:inline">FirstIn</span>
          </Link>
          <DemoTabs />
          <Link href="/signup" className="ms-auto rounded-lg bg-accent px-3 py-1.5 text-sm font-semibold text-white hover:opacity-90">
            Get started
          </Link>
        </div>
      </header>
      <main className="mx-auto max-w-6xl px-4 py-6">{children}</main>
    </div>
  );
}
